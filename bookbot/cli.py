"""Command-line interface — input collection, display, and main loop."""

import re
import logging

from bookbot.recommender import (
    FAMILIARITY_MAP,
    MAX_RETRIES,
    SYSTEM_PROMPT,
    build_user_prompt,
    call_llm,
    parse_llm_output,
    validate_recommendations,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ALLOWED_GENRES = [
    "science fiction",
    "fantasy",
    "mystery",
    "thriller",
    "romance",
    "nonfiction",
    "historical",
]

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


# ===================================================================
# LAYER 1: INPUT VALIDATION
# ===================================================================
def _is_valid_book_title(title: str) -> bool:
    """Return True if the string looks like a reasonable book title."""
    if not title or len(title) > MAX_STRING_LENGTH:
        return False
    # reject strings that are only symbols / punctuation
    if not re.search(r"[a-zA-Z0-9]", title):
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
    while True:
        print(f"Pick your flavor(s): {', '.join(ALLOWED_GENRES)}")
        raw = input("What genres do you vibe with? (1-3, comma-separated): ").strip()

        if not raw:
            print("Oops — you didn't type anything! Give me at least one genre.")
            continue

        parts = [g.strip().lower() for g in raw.split(",") if g.strip()]

        if len(parts) < 1 or len(parts) > 3:
            print("Whoa there — I can handle 1 to 3 genres, no more, no less!")
            continue

        invalid = [g for g in parts if g not in ALLOWED_GENRES]
        if invalid:
            print(f"Hmm, I don't recognize: {', '.join(invalid)}")
            print(f"I only speak these genres: {', '.join(ALLOWED_GENRES)}")
            continue

        if len(parts) != len(set(parts)):
            print("You listed the same genre twice — I like your enthusiasm, but let's keep them unique!")
            continue

        return parts


def validate_books() -> list[str]:
    """Prompt the user for 2-3 favorite books.
    Re-prompts on invalid input until valid."""
    while True:
        raw = input("Name 2-3 books you absolutely love (comma-separated): ").strip()

        if not raw:
            print("Oops — you didn't type anything! Tell me about some books you love.")
            continue

        # Content filter: reject prompt-injection attempts
        if _contains_prompt_injection(raw):
            logging.warning("Prompt injection attempt detected: %s", raw)
            print("Nice try, but that doesn't look like a book title to me!")
            continue

        parts = [b.strip() for b in raw.split(",") if b.strip()]

        if len(parts) < 2 or len(parts) > 3:
            print("I need exactly 2 or 3 books, no more, no less!")
            continue

        bad = [b for b in parts if not _is_valid_book_title(b)]
        if bad:
            print(
                f"Hmm, these don't look like real titles: {bad}. "
                f"Book titles should have actual words and be under {MAX_STRING_LENGTH} characters."
            )
            continue

        return parts


def validate_familiarity() -> int:
    """Prompt the user for a familiarity preference (1-4).
    Re-prompts on invalid input until valid."""
    while True:
        print("How adventurous are you feeling today?")
        print("  1 = Play it safe")
        print("  2 = Mostly classics, maybe one wild card")
        print("  3 = Half-and-half — familiar + fresh")
        print("  4 = Surprise me!")
        raw = input("Pick a number (1-4): ").strip()

        if not raw:
            print("Oops, you left that blank! Just type a number from 1 to 4.")
            continue

        try:
            choice = int(raw)
        except ValueError:
            print("That's not a number! I need a digit between 1 and 4.")
            continue

        if choice not in FAMILIARITY_MAP:
            print("I can only count to 4 on this one — pick 1, 2, 3, or 4.")
            continue

        return choice


def collect_preferences() -> dict:
    """Run all three input validators and return validated preferences."""
    print("=" * 55)
    print("Hey there! I'm BookBot, your personal book recommender. Let's find your next read!")
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
    print("Ta-da! Here are your BookBot picks:")
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
def generate_recommendations(user_prompt: str, prefs: dict) -> bool:
    """Run Layers 3-5: call LLM, parse, validate, and display.
    Returns True on success, False if all attempts failed."""
    for attempt in range(1, MAX_RETRIES + 1):
        print("Rummaging through the shelves...")

        # Layer 3: LLM Call
        raw = call_llm(SYSTEM_PROMPT, user_prompt)
        if raw is None:
            logging.error("LLM call returned None on attempt %d", attempt)
            if attempt < MAX_RETRIES:
                print("Something went wrong with the LLM. Retrying...")
                continue
            break

        # Layer 4: Output Parsing
        parsed = parse_llm_output(raw)
        if parsed is None:
            logging.error("Parsing failed on attempt %d", attempt)
            if attempt < MAX_RETRIES:
                print("Could not parse LLM response. Retrying...")
                continue
            break

        # Layer 5: Business Logic Validation
        final = validate_recommendations(parsed, prefs)
        if final is None:
            logging.error("Business validation failed on attempt %d", attempt)
            if attempt < MAX_RETRIES:
                print("Those recommendations didn't pass my quality check. One more try...")
                continue
            break

        # Success!
        display_recommendations(final)
        return True

    # All attempts exhausted
    print("\nSorry, BookBot couldn't generate valid recommendations right now.")
    print("Please try again later.\n")
    logging.error("All attempts exhausted. No valid recommendations produced.")
    return False


def main() -> None:
    """BookBot entry point."""
    # --- Layer 1: Input Validation ---
    prefs = collect_preferences()

    # --- Layer 2: Prompt Construction ---
    user_prompt = build_user_prompt(prefs)
    logging.info("User prompt:\n%s", user_prompt)

    # --- Generate, display, and offer more ---
    while True:
        success = generate_recommendations(user_prompt, prefs)

        if not success:
            break

        # Ask if the user wants another round
        answer = input("\nWould you like more recommendations? (yes/no): ").strip().lower()
        if answer in ("yes", "y"):
            print("\nGood choice! Let me dig up more...\n")
            continue
        else:
            print("\nHappy reading! Come back any time you need a fresh stack :D")
            break
