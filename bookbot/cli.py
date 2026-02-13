"""Command-line interface — input collection, display, and main loop."""

import re
import logging

from bookbot.i18n import (
    set_language,
    get_language,
    t,
    genre_display_names,
    lookup_genre,
)
from bookbot.recommender import (
    FAMILIARITY_MAP,
    MAX_RETRIES,
    get_system_prompt,
    build_user_prompt,
    call_llm,
    parse_llm_output,
    validate_recommendations,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_STRING_LENGTH = 200  # reject absurdly long input strings

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


def _split_by_comma(text: str) -> list[str]:
    """Split input by the appropriate comma for the active language."""
    if get_language() == "zh":
        return [s.strip() for s in text.split("，") if s.strip()]
    return [s.strip() for s in text.split(",") if s.strip()]


def _join_by_comma(items: list[str]) -> str:
    """Join items with the appropriate separator for the active language."""
    if get_language() == "zh":
        return "、".join(items)
    return ", ".join(items)


# ===================================================================
# LANGUAGE SELECTION
# ===================================================================
def select_language() -> None:
    """Prompt the user to pick English or Chinese at startup."""
    while True:
        print(t("lang_prompt"))
        print(t("lang_option_1"))
        print(t("lang_option_2"))
        raw = input(t("lang_input")).strip()
        if raw == "1":
            set_language("en")
            return
        elif raw == "2":
            set_language("zh")
            return
        else:
            print(t("lang_invalid"))


# ===================================================================
# LAYER 1: INPUT VALIDATION
# ===================================================================
def _is_valid_book_title(title: str) -> bool:
    """Return True if the string looks like a reasonable book title."""
    if not title or len(title) > MAX_STRING_LENGTH:
        return False
    # reject strings that are only symbols / punctuation
    # allow Latin letters, digits, and CJK characters
    if not re.search(r"[a-zA-Z0-9\u4e00-\u9fff]", title):
        return False
    return True


def _contains_prompt_injection(text: str) -> bool:
    """Return True if text matches any known prompt-injection pattern."""
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def validate_genres() -> list[str]:
    """Prompt the user for 1-3 genres from the allowed list.
    Re-prompts on invalid input until valid."""
    display_names = genre_display_names()

    while True:
        print(t("genre_list", genres=_join_by_comma(display_names)))
        raw = input(t("genre_prompt")).strip()

        if not raw:
            print(t("genre_empty"))
            continue

        parts = [g.lower() for g in _split_by_comma(raw)]

        if len(parts) < 1 or len(parts) > 3:
            print(t("genre_count"))
            continue

        # Map display names to internal names
        internal_names = []
        invalid = []
        for g in parts:
            mapped = lookup_genre(g)
            if mapped is None:
                invalid.append(g)
            else:
                internal_names.append(mapped)

        if invalid:
            print(t("genre_invalid", invalid=_join_by_comma(invalid)))
            print(t("genre_allowed", genres=_join_by_comma(display_names)))
            continue

        if len(internal_names) != len(set(internal_names)):
            print(t("genre_dup"))
            continue

        return internal_names


def validate_books() -> list[str]:
    """Prompt the user for 2-3 favorite books.
    Re-prompts on invalid input until valid."""
    while True:
        raw = input(t("book_prompt")).strip()

        if not raw:
            print(t("book_empty"))
            continue

        # Content filter: reject prompt-injection attempts
        if _contains_prompt_injection(raw):
            logging.warning("Prompt injection attempt detected: %s", raw)
            print(t("book_injection"))
            continue

        parts = _split_by_comma(raw)

        if len(parts) < 2 or len(parts) > 3:
            print(t("book_count"))
            continue

        bad = [b for b in parts if not _is_valid_book_title(b)]
        if bad:
            print(t("book_invalid", bad=bad, max_len=MAX_STRING_LENGTH))
            continue

        return parts


def validate_familiarity() -> int:
    """Prompt the user for a familiarity preference (1-4).
    Re-prompts on invalid input until valid."""
    while True:
        print(t("fam_header"))
        print(t("fam_1"))
        print(t("fam_2"))
        print(t("fam_3"))
        print(t("fam_4"))
        raw = input(t("fam_prompt")).strip()

        if not raw:
            print(t("fam_empty"))
            continue

        try:
            choice = int(raw)
        except ValueError:
            print(t("fam_nan"))
            continue

        if choice not in FAMILIARITY_MAP:
            print(t("fam_range"))
            continue

        return choice


def collect_preferences() -> dict:
    """Run all three input validators and return validated preferences."""
    print("=" * 55)
    print(t("welcome"))
    print("=" * 55, "\n")

    genres = validate_genres()
    print()
    books = validate_books()
    print()
    familiarity = validate_familiarity()
    print()

    preferences = {
        "genres": genres,
        "favorite_books": books,
        "familiarity_level": familiarity,
    }
    logging.info("Validated preferences: %s", preferences)
    return preferences


# ===================================================================
# DISPLAY
# ===================================================================
def display_recommendations(recs: list[dict]) -> None:
    """Pretty-print the final recommendations."""
    print("\n" + "=" * 55)
    print(t("rec_header"))
    print("=" * 55)
    for i, rec in enumerate(recs, 1):
        print(f"\n  {i}. {rec['title']} by {rec['author']} "
              f"({rec['publication_year']})")
        print(f"     {rec['explanation']}")
    print()
    print("=" * 55)


# ===================================================================
# ORCHESTRATION
# ===================================================================
def _filter_duplicates(recs: list[dict], already: list[str]) -> list[dict]:
    """Remove recommendations whose titles have already been suggested."""
    if not already:
        return recs
    seen = {title.strip().lower() for title in already}
    filtered = [r for r in recs if r["title"].strip().lower() not in seen]
    removed = len(recs) - len(filtered)
    if removed:
        logging.info("Removed %d duplicate(s) that were already recommended.", removed)
    return filtered


def generate_recommendations(
    user_prompt: str,
    prefs: dict,
    already_recommended: list[str] | None = None,
) -> list[dict] | None:
    """Run Layers 3-5: call LLM, parse, validate, and display.
    Returns the list of recommendations on success, or None if all attempts failed.

    *already_recommended* is a list of titles from previous rounds;
    any duplicates are stripped from the result before display.
    """
    system_prompt = get_system_prompt()
    already = already_recommended or []

    for attempt in range(1, MAX_RETRIES + 1):
        print(t("searching"))

        # Layer 3: LLM Call
        raw = call_llm(system_prompt, user_prompt)
        if raw is None:
            logging.error("LLM call returned None on attempt %d", attempt)
            if attempt < MAX_RETRIES:
                print(t("retry_llm"))
                continue
            break

        # Layer 4: Output Parsing
        parsed = parse_llm_output(raw)
        if parsed is None:
            logging.error("Parsing failed on attempt %d", attempt)
            if attempt < MAX_RETRIES:
                print(t("retry_parse"))
                continue
            break

        # Layer 5: Business Logic Validation
        final = validate_recommendations(parsed, prefs)
        if final is None:
            logging.error("Business validation failed on attempt %d", attempt)
            if attempt < MAX_RETRIES:
                print(t("retry_validate"))
                continue
            break

        # Layer 6: Duplicate Check — remove already-recommended titles
        final = _filter_duplicates(final, already)
        if not final:
            logging.warning("All recommendations were duplicates on attempt %d", attempt)
            if attempt < MAX_RETRIES:
                continue
            break

        # Success!
        display_recommendations(final)
        return final

    # All attempts exhausted
    print(f"\n{t('fail_all')}")
    print(f"{t('fail_later')}\n")
    logging.error("All attempts exhausted. No valid recommendations produced.")
    return None


def main() -> None:
    """BookBot entry point."""
    # --- Language Selection ---
    select_language()
    print()

    # --- Layer 1: Input Validation ---
    prefs = collect_preferences()

    # --- Generate, display, and offer more ---
    already_recommended: list[str] = []

    while True:
        # --- Layer 2: Prompt Construction (rebuilt each round) ---
        user_prompt = build_user_prompt(prefs, exclude=already_recommended or None)
        logging.info("User prompt:\n%s", user_prompt)

        recs = generate_recommendations(user_prompt, prefs, already_recommended)

        if recs is None:
            break

        # Track titles so the next round excludes them
        already_recommended.extend(rec["title"] for rec in recs)

        # Ask if the user wants another round (exact yes/no or 是/否)
        while True:
            answer = input(t("more_prompt")).strip()
            if answer in ("yes", "是"):
                print(t("more_yes"))
                break
            elif answer in ("no", "否"):
                print(t("more_no"))
                break
            else:
                print(t("more_invalid"))

        if answer in ("no", "否"):
            break
