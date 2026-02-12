# BookBot

A CLI book recommendation assistant powered by OpenAI. Tell BookBot your favorite genres, a few books you love, and how adventurous you're feeling — it'll suggest 3-5 personalized picks.

## Architecture

BookBot uses a **5-layer pipeline** to turn user preferences into validated recommendations:

| Layer | Purpose |
|-------|---------|
| 1. Input Validation | Collects user preferences interactively — genre selection (1–3 from 7 allowed genres), favorite books (2–3 titles), and a familiarity/adventurousness level (1–4 scale). Includes prompt-injection detection via regex patterns and input sanitization. |
| 2. Prompt Construction | Builds a system prompt (personality + strict JSON output format) and a user prompt from validated preferences. |
| 3. LLM Call | Sends the prompt to OpenAI with retry logic (up to 3 attempts), handling empty responses and API exceptions. |
| 4. Output Parsing | Robust JSON extraction — handles raw JSON, markdown-fenced JSON, trailing commas, and nested brace extraction. |
| 5. Business Validation | Validates each recommendation (required fields, type checks, publication year 1450–2026, explanation length bounds), deduplicates by title, and enforces 3–5 results. |

```
bookbot/
├── __init__.py        # package init, logging config
├── __main__.py        # python -m bookbot entry point
├── cli.py             # Layer 1 + display + main loop
└── recommender.py     # Layers 2-5 (the engine)
```

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/kemilii/bookbot.git
cd bookbot

# 2. Install dependencies
pip install -r requirements.txt

# 4. Set up your API key
cp .env.example .env
# Edit .env and paste your OpenAI API key

# 5. Run BookBot
python -m bookbot
```

## Configuration

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Your OpenAI API key (required) |

