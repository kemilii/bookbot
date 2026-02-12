"""Core recommendation engine — prompt construction, LLM calls, parsing, and validation."""

from dotenv import load_dotenv
from openai import OpenAI
import json
import re
import logging

load_dotenv()

client = OpenAI()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_RETRIES = 3  # total LLM attempts before giving up

FAMILIARITY_MAP = {
    1: "very familiar, well-known classics and bestsellers",
    2: "mostly familiar titles with a few lesser-known picks",
    3: "a mix of familiar favorites and hidden gems",
    4: "surprise me with unexpected, lesser-known books",
}

SYSTEM_PROMPT = """\
You are BookBot — a witty, warm, and slightly nerdy book recommendation assistant.
Your personality is a bit of humorous and friendly; you genuinely love books and get excited sharing them.
You MUST reply with ONLY a single JSON object — no prose, no markdown, no explanation outside the JSON.
The JSON object must have exactly one key: "recommendations", whose value is an array of 3 to 5 objects.
Each object must have these keys:
  - "title"            (string)
  - "author"           (string)
  - "publication_year" (integer)
  - "explanation"      (string, 1-3 sentences in a conversational tone explaining why this book fits the user's taste)
Do NOT include any text outside the JSON object."""


# ===================================================================
# LAYER 2: PROMPT CONSTRUCTION
# ===================================================================
def build_user_prompt(prefs: dict) -> str:
    """Build the user-side prompt from validated preferences."""
    genres_str = ", ".join(prefs["genres"])
    books_str = ", ".join(prefs["favorite_books"])
    fam_desc = FAMILIARITY_MAP[prefs["familiarity_level"]]

    return (
        f"I enjoy these genres: {genres_str}.\n"
        f"Some books I love: {books_str}.\n"
        f"For familiarity, I'd like: {fam_desc}.\n\n"
        "Please recommend 3 to 5 books as a single JSON object with key "
        '"recommendations" containing an array of objects with keys: '
        "title, author, publication_year, explanation."
    )


# ===================================================================
# LAYER 3: LLM CALL
# ===================================================================
def call_llm(system_prompt: str, user_prompt: str) -> str | None:
    """Send the prompt to the LLM. Retries on failure.
    Returns raw string output or None on unrecoverable error."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logging.info("LLM call attempt %d", attempt)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=1024,
            )
            raw = response.choices[0].message.content
            if not raw or not raw.strip():
                logging.warning("Empty LLM response on attempt %d", attempt)
                continue
            logging.info("LLM raw output (attempt %d): %s", attempt, raw)
            return raw

        except Exception as exc:
            logging.error("LLM call error (attempt %d): %s", attempt, exc)
            if attempt < MAX_RETRIES:
                print("  (Retrying LLM call...)")
                continue

    logging.error("All LLM call attempts failed.")
    return None


# ===================================================================
# LAYER 4: OUTPUT PARSING
# ===================================================================
def parse_llm_output(raw: str) -> dict | None:
    """Extract a JSON object from the LLM's raw text.
    Handles pure JSON, markdown-fenced JSON, and extra surrounding text.
    Returns parsed dict or None."""

    # Step 1: strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"```", "", cleaned).strip()

    # Step 2: try direct parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Step 3: locate first { ... } block (greedy to capture nested braces)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Step 4: minimal cleanup attempt (trailing commas, etc.)
    if match:
        attempt = match.group()
        attempt = re.sub(r",\s*([}\]])", r"\1", attempt)  # trailing commas
        try:
            data = json.loads(attempt)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    logging.error("Output parsing failed. Raw output preserved:\n%s", raw)
    return None


# ===================================================================
# LAYER 5: BUSINESS LOGIC VALIDATION
# ===================================================================
def validate_recommendation(rec: dict, prefs: dict) -> bool:
    """Return True if a single recommendation dict is valid."""
    # Required fields
    for field in ("title", "author", "publication_year", "explanation"):
        if field not in rec:
            logging.warning("Missing field '%s' in recommendation: %s", field, rec)
            return False

    if not isinstance(rec["title"], str) or not rec["title"].strip():
        return False
    if not isinstance(rec["author"], str) or not rec["author"].strip():
        return False
    if not isinstance(rec["explanation"], str) or not rec["explanation"].strip():
        return False

    # Publication year sanity
    try:
        year = int(rec["publication_year"])
    except (ValueError, TypeError):
        logging.warning("Invalid publication_year: %s", rec["publication_year"])
        return False
    if year < 1450 or year > 2026:
        logging.warning("Suspicious year %d for '%s'", year, rec["title"])
        return False

    # Explanation length bounds (at least 10 chars, at most 1000)
    if len(rec["explanation"]) < 10 or len(rec["explanation"]) > 1000:
        logging.warning("Explanation length out of bounds for '%s'", rec["title"])
        return False

    return True


def validate_recommendations(parsed: dict, prefs: dict) -> list[dict] | None:
    """Validate the full parsed response.
    Returns a list of 3-5 valid recommendations or None."""

    recs = parsed.get("recommendations")
    if not isinstance(recs, list):
        logging.error("'recommendations' key missing or not a list.")
        return None

    # Truncate if more than 5
    if len(recs) > 5:
        logging.info("Received %d recommendations; truncating to 5.", len(recs))
        recs = recs[:5]

    # Validate each
    valid = [r for r in recs if validate_recommendation(r, prefs)]

    # Check for duplicate titles
    seen = set()
    deduped = []
    for r in valid:
        key = r["title"].strip().lower()
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    if len(deduped) < len(valid):
        logging.warning("Duplicate titles removed.")
    valid = deduped

    if len(valid) < 3:
        logging.error("Only %d valid recommendations (need 3).", len(valid))
        return None

    return valid[:5]
