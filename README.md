# BookBot

A book recommendation assistant powered by OpenAI. Tell BookBot your favorite genres, a few books you love, and how adventurous you're feeling — it'll suggest 3–5 personalized picks. Available as both a **CLI** and a **web UI**. Supports **English** and **Chinese (中文)**.

## Architecture

BookBot uses a **5-layer pipeline** to turn user preferences into validated recommendations:

| Layer | Purpose |
|-------|---------|
| 0. Language Selection | Prompts the user to choose English or Chinese at startup. All subsequent prompts, messages, and LLM output adapt to the selected language. |
| 1. Input Validation | Collects user preferences interactively — genre selection (1–3 from 7 allowed genres), favorite books (2–3 titles), and a familiarity/adventurousness level (1–4 scale). Includes prompt-injection detection via regex patterns and input sanitization. Accepts Chinese characters in book titles and Chinese commas (`，`) as separators. |
| 2. Prompt Construction | Builds a language-appropriate system prompt and a user prompt from validated preferences. On subsequent rounds, appends an exclusion list of previously recommended titles. |
| 3. LLM Call | Sends the prompt to OpenAI (`gpt-4o`) with retry logic (up to 3 attempts), handling empty responses and API exceptions. |
| 4. Output Parsing | Robust JSON extraction — handles raw JSON, markdown-fenced JSON, trailing commas, and nested brace extraction. |
| 5. Business Validation | Validates each recommendation (required fields, type checks, publication year 1450–2026, explanation length bounds), deduplicates by title, and enforces 3–5 results. Filters out any titles that were already recommended in previous rounds. If all results are duplicates, silently retries the LLM. |

```
bookbot/
├── __init__.py        # package init, logging config
├── __main__.py        # python -m bookbot entry point
├── i18n.py            # internationalization (English + Chinese strings, genre mappings)
├── cli.py             # language selection, Layer 1, display, duplicate check, main loop
├── recommender.py     # Layers 2-5 (prompt construction, LLM call, parsing, validation)
├── web.py             # Flask web UI (routes + API)
└── templates/
    └── index.html     # single-page web interface
```

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/kemilii/bookbot.git
cd bookbot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up your API key
cp .env.example .env
# Edit .env and paste your OpenAI API key

# 4a. Run the CLI
python -m bookbot

# 4b. Or run the Web UI
python -m bookbot.web
```

### CLI

On launch you'll see:

```
Choose your language / 选择语言:
  1 = English
  2 = 中文
Enter 1 or 2 / 输入 1 或 2:
```

After choosing a language, BookBot walks you through genre selection, favorite books, and familiarity level, then returns 3–5 personalized recommendations. You can ask for more rounds — previously recommended books are automatically excluded.

### Web UI

Run `python -m bookbot.web` and open **http://127.0.0.1:5000** in your browser. The web interface provides a clean step-by-step wizard: pick a language, select genres, enter favorite books, choose your adventurousness level, and get recommendations displayed as cards. You can request additional rounds — previously recommended titles are automatically excluded.

## Configuration

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Your OpenAI API key (required) |
