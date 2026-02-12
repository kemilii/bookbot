# BookBot

A CLI book recommendation assistant powered by OpenAI. Tell BookBot your favorite genres, a few books you love, and how adventurous you're feeling — it'll suggest 3-5 personalized picks.

## Architecture

BookBot uses a **5-layer pipeline** to turn user preferences into validated recommendations:

| Layer | Module | Responsibility |
|-------|--------|----------------|
| 1 — Input Validation | `cli.py` | Collects & sanitizes user preferences (genres, books, familiarity) with prompt-injection detection |
| 2 — Prompt Construction | `recommender.py` | Builds system + user prompts from validated preferences |
| 3 — LLM Call | `recommender.py` | Sends prompts to OpenAI with retry logic |
| 4 — Output Parsing | `recommender.py` | Extracts JSON from raw LLM text (handles fences, trailing commas, etc.) |
| 5 — Business Validation | `recommender.py` | Validates fields, types, year ranges, deduplicates, enforces 3-5 results |

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

