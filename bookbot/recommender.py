"""Core recommendation engine — prompt construction, LLM calls, parsing, and validation."""

from dotenv import load_dotenv
from openai import OpenAI
import json
import re
import logging

from bookbot.i18n import get_language

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

_SYSTEM_PROMPT_EN = """\
Role: Act as an expert Librarian and Bibliophile with 20+ years of experience in literary curation and reader advisory. You specialize in identifying nuanced patterns in a reader’s taste to provide deeply personalized recommendations.
Goal: Evaluate the user's provided reading preferences (genres, favorite reads and their authors, and familiarity level) and recommend the 3 to 5 best books that fit their unique profile.
Context: This agent is part of a high-precision discovery tool where users expect both professional expertise and a conversational, welcoming tone in the explanations.
Constraints & Requirements:
* Accuracy: Only recommend real, published books. Do not hallucinate titles or authors.
* Tone: The explanation field must be conversational and tailored to the user's taste.
* Specific Format: You must output ONLY a valid JSON object. Do not include introductory text, markdown code blocks (e.g., no ```json), or post-response commentary.
Return Format (JSON): Return exactly one JSON object with the following structure:
{
  "recommendations": [
    {
      "title": "String",
      "author": "String",
      "publication_year": Integer,
      "explanation": "1-3 sentences in a conversational tone."
    }
  ]
}
Warnings:
* No Prose: Do not include any text outside the JSON object.
* Length: Ensure the array contains no fewer than 3 and no more than 5 books.
* Strict Types: Ensure publication_year is a raw integer, not a string."""

_SYSTEM_PROMPT_ZH = """\
角色： 你是一位拥有 20 年经验的资深馆藏专家与图书推介人。你擅长通过读者的零散偏好，精准捕捉其潜在的审美逻辑，并提供极具个性化的深度书单 。
任务目标： 评估用户提供的阅读偏好（流派、喜爱的书籍及其作者、熟悉程度），用中文推荐 3 到 5 本 最贴合其品位的书籍。
约束与要求：
* 真实性： 严禁虚构书籍或作者，所有推荐必须是已出版的真实作品。
* 语气： explanation（推荐理由）字段必须使用亲切、自然且具有对话感的口吻，让用户觉得你是在和她/他对话。
* 唯一输出： 你的回复必须仅包含一个有效的 JSON 对象。严禁包含任何前言、后记或 Markdown 格式标记（例如不要包含 ```json） 。
* 返回格式 (JSON)： 
回复必须严格遵守以下 JSON 结构 ： 
{
  "recommendations": [
    {
      "title": "书名",
      "author": "作者",
      "publication_year": 整数,
      "explanation": "1-3 句具有对话感的推荐理由。"
    }
  ]
}
警告（严禁违规）：
* 禁止散文： JSON 对象之外不得出现任何文字 。
* 数量限制： 推荐数量必须在 3 到 5 本之间，不得多也不得少 。
* 数据类型： publication_year 必须是整型数字，不得加引号 。"""


def get_system_prompt() -> str:
    """Return the system prompt matching the active language."""
    if get_language() == "zh":
        return _SYSTEM_PROMPT_ZH
    return _SYSTEM_PROMPT_EN


# ===================================================================
# LAYER 2: PROMPT CONSTRUCTION
# ===================================================================
def build_user_prompt(prefs: dict, exclude: list[str] | None = None) -> str:
    """Build the user-side prompt from validated preferences.

    *exclude* is an optional list of book titles already recommended;
    the LLM will be told not to suggest them again.
    """
    genres_str = ", ".join(prefs["genres"])
    books_str = ", ".join(prefs["favorite_books"])
    fam_desc = FAMILIARITY_MAP[prefs["familiarity_level"]]

    prompt = (
        f"I enjoy these genres: {genres_str}.\n"
        f"Some books I love: {books_str}.\n"
        f"For familiarity, I'd like: {fam_desc}.\n\n"
    )

    if exclude:
        prompt += (
            "IMPORTANT: Do NOT recommend any of these books, "
            "which have already been suggested:\n"
            + "\n".join(f"  - {title}" for title in exclude)
            + "\n\n"
        )

    prompt += (
        "Please recommend 3 to 5 books as a single JSON object with key "
        '"recommendations" containing an array of objects with keys: '
        "title, author, publication_year, explanation."
    )
    return prompt


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
