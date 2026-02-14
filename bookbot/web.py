"""Flask web interface for BookBot."""

import logging
import re

from flask import Flask, render_template, request, jsonify

from bookbot.database import (
    init_db,
    add_subscription,
    deactivate_subscription,
)
from bookbot.i18n import (
    set_language,
    get_language,
    t,
    genre_display_names,
    lookup_genre,
    GENRE_DISPLAY,
)
from bookbot.recommender import (
    FAMILIARITY_MAP,
    get_system_prompt,
    build_user_prompt,
    call_llm,
    parse_llm_output,
    validate_recommendations,
)
from bookbot.scheduler import start_scheduler

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Constants (mirrored from cli.py for web-side validation)
# ---------------------------------------------------------------------------
MAX_STRING_LENGTH = 200

PROMPT_INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"pretend you are",
    r"disregard.*prompt",
    r"forget your instructions",
    r"you are now",
    r"act as if",
    r"new persona",
    r"override.*system",
]


def _is_valid_book_title(title: str) -> bool:
    if not title or len(title) > MAX_STRING_LENGTH:
        return False
    if not re.search(r"[a-zA-Z0-9\u4e00-\u9fff]", title):
        return False
    return True


def _contains_prompt_injection(text: str) -> bool:
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _filter_duplicates(recs: list[dict], already: list[str]) -> list[dict]:
    if not already:
        return recs
    seen = {title.strip().lower() for title in already}
    return [r for r in recs if r["title"].strip().lower() not in seen]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """Serve the main single-page application."""
    return render_template("index.html")


@app.route("/api/genres")
def api_genres():
    """Return genre lists for both languages."""
    return jsonify({
        "en": list(GENRE_DISPLAY["en"].values()),
        "zh": list(GENRE_DISPLAY["zh"].values()),
        "internal": {
            lang: {display: internal for internal, display in mapping.items()}
            for lang, mapping in GENRE_DISPLAY.items()
        },
    })


@app.route("/api/recommend", methods=["POST"])
def api_recommend():
    """Accept preferences and return book recommendations.

    Expected JSON body:
    {
        "language": "en" | "zh",
        "genres": ["science fiction", "fantasy"],   // display names
        "books": ["Book One", "Book Two"],
        "familiarity": 1-4,
        "exclude": ["Already Recommended Title"]     // optional
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    # --- Language ---
    lang = data.get("language", "en")
    if lang not in ("en", "zh"):
        return jsonify({"error": "Unsupported language"}), 400
    set_language(lang)

    # --- Genres ---
    genres_raw = data.get("genres", [])
    if not isinstance(genres_raw, list) or not (1 <= len(genres_raw) <= 3):
        return jsonify({"error": t("genre_count")}), 400

    internal_genres = []
    for g in genres_raw:
        mapped = lookup_genre(g)
        if mapped is None:
            return jsonify({"error": f"Unknown genre: {g}"}), 400
        internal_genres.append(mapped)

    if len(internal_genres) != len(set(internal_genres)):
        return jsonify({"error": t("genre_dup")}), 400

    # --- Books ---
    books = data.get("books", [])
    if not isinstance(books, list) or not (2 <= len(books) <= 3):
        return jsonify({"error": t("book_count")}), 400

    for b in books:
        if not _is_valid_book_title(b):
            return jsonify({"error": f"Invalid book title: {b}"}), 400
        if _contains_prompt_injection(b):
            return jsonify({"error": t("book_injection")}), 400

    # --- Familiarity ---
    familiarity = data.get("familiarity")
    try:
        familiarity = int(familiarity)
    except (TypeError, ValueError):
        return jsonify({"error": t("fam_nan")}), 400
    if familiarity not in FAMILIARITY_MAP:
        return jsonify({"error": t("fam_range")}), 400

    # --- Build preferences ---
    prefs = {
        "genres": internal_genres,
        "favorite_books": books,
        "familiarity_level": familiarity,
    }

    exclude = data.get("exclude", [])
    user_prompt = build_user_prompt(prefs, exclude=exclude or None)
    logging.info("Web request — user prompt:\n%s", user_prompt)

    # --- Call recommender pipeline ---
    system_prompt = get_system_prompt()
    max_retries = 3

    for attempt in range(1, max_retries + 1):
        raw = call_llm(system_prompt, user_prompt)
        if raw is None:
            continue

        parsed = parse_llm_output(raw)
        if parsed is None:
            continue

        final = validate_recommendations(parsed, prefs)
        if final is None:
            continue

        final = _filter_duplicates(final, exclude)
        if not final:
            continue

        return jsonify({"recommendations": final})

    return jsonify({"error": t("fail_all")}), 500


# ---------------------------------------------------------------------------
# Subscription routes
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


_VALID_FREQUENCIES = ("daily", "weekly", "monthly")


@app.route("/api/subscribe", methods=["POST"])
def api_subscribe():
    """Subscribe to scheduled recommendations.

    Expected JSON body:
    {
        "email": "user@example.com",
        "language": "en" | "zh",
        "genres": ["science fiction", "fantasy"],
        "books": ["Book One", "Book Two"],
        "familiarity": 1-4,
        "frequency": "daily" | "weekly" | "monthly"
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    # --- Email ---
    email = (data.get("email") or "").strip().lower()
    if not email or not _EMAIL_RE.match(email):
        return jsonify({"error": t("sub_email_invalid")}), 400

    # --- Language ---
    lang = data.get("language", "en")
    if lang not in ("en", "zh"):
        return jsonify({"error": "Unsupported language"}), 400
    set_language(lang)

    # --- Frequency ---
    frequency = data.get("frequency", "monthly")
    if frequency not in _VALID_FREQUENCIES:
        return jsonify({"error": t("sub_freq_invalid")}), 400

    # --- Genres ---
    genres_raw = data.get("genres", [])
    if not isinstance(genres_raw, list) or not (1 <= len(genres_raw) <= 3):
        return jsonify({"error": t("genre_count")}), 400

    internal_genres = []
    for g in genres_raw:
        mapped = lookup_genre(g)
        if mapped is None:
            return jsonify({"error": f"Unknown genre: {g}"}), 400
        internal_genres.append(mapped)

    if len(internal_genres) != len(set(internal_genres)):
        return jsonify({"error": t("genre_dup")}), 400

    # --- Books ---
    books = data.get("books", [])
    if not isinstance(books, list) or not (2 <= len(books) <= 3):
        return jsonify({"error": t("book_count")}), 400

    for b in books:
        if not _is_valid_book_title(b):
            return jsonify({"error": f"Invalid book title: {b}"}), 400
        if _contains_prompt_injection(b):
            return jsonify({"error": t("book_injection")}), 400

    # --- Familiarity ---
    familiarity = data.get("familiarity")
    try:
        familiarity = int(familiarity)
    except (TypeError, ValueError):
        return jsonify({"error": t("fam_nan")}), 400
    if familiarity not in FAMILIARITY_MAP:
        return jsonify({"error": t("fam_range")}), 400

    # --- Persist ---
    try:
        token = add_subscription(email, lang, internal_genres, books, familiarity, frequency)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409

    logging.info("Subscription created for %s (frequency=%s)", email, frequency)
    return jsonify({"message": t("sub_success", email=email), "token": token}), 201


@app.route("/api/unsubscribe/<token>")
def api_unsubscribe(token):
    """Unsubscribe using a unique token."""
    success = deactivate_subscription(token)
    if success:
        return render_template("unsubscribe.html", success=True)
    return render_template("unsubscribe.html", success=False), 404


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run():
    """Start the Flask development server."""
    init_db()
    start_scheduler()
    print("\n  BookBot Web UI starting...")
    print("  Open http://127.0.0.1:8000 in your browser\n")
    app.run(debug=True, port=8000, use_reloader=False)


if __name__ == "__main__":
    run()
