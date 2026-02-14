"""Internationalization — English and Chinese UI strings for BookBot."""

# ---------------------------------------------------------------------------
# Active language (module-level state)
# ---------------------------------------------------------------------------
_lang: str = "en"


def set_language(lang: str) -> None:
    """Set the active language ('en' or 'zh')."""
    global _lang
    if lang not in ("en", "zh"):
        raise ValueError(f"Unsupported language: {lang}")
    _lang = lang


def get_language() -> str:
    """Return the current language code."""
    return _lang


def t(key: str, **kwargs) -> str:
    """Look up a translated string by *key* in the active language.

    Supports ``str.format`` placeholders, e.g. ``t("genre_invalid", invalid="xyz")``.
    Falls back to English if the key is missing in the active language.
    """
    text = STRINGS.get(_lang, STRINGS["en"]).get(key)
    if text is None:
        text = STRINGS["en"].get(key, f"[missing:{key}]")
    return text.format(**kwargs) if kwargs else text


# ---------------------------------------------------------------------------
# Genre mappings  (internal English name <-> display name per language)
# ---------------------------------------------------------------------------
GENRE_DISPLAY: dict[str, dict[str, str]] = {
    "en": {
        "science fiction": "science fiction",
        "fantasy": "fantasy",
        "mystery": "mystery",
        "thriller": "thriller",
        "romance": "romance",
        "nonfiction": "nonfiction",
        "historical": "historical",
        "feminism": "feminism",
        "psychology": "psychology",
    },
    "zh": {
        "science fiction": "科幻",
        "fantasy": "奇幻",
        "mystery": "悬疑",
        "thriller": "惊悚",
        "romance": "爱情",
        "nonfiction": "非虚构",
        "historical": "历史",
        "feminism": "女性主义",
        "psychology": "心理学",
    },
}

# Reverse lookup: display name -> internal name
GENRE_LOOKUP: dict[str, dict[str, str]] = {
    lang: {display: internal for internal, display in mapping.items()}
    for lang, mapping in GENRE_DISPLAY.items()
}


def genre_display_names() -> list[str]:
    """Return the list of genre display names in the active language."""
    return list(GENRE_DISPLAY.get(_lang, GENRE_DISPLAY["en"]).values())


def lookup_genre(user_input: str) -> str | None:
    """Map a user-typed genre name (in the active language) to the internal
    English name.  Returns None if unrecognised."""
    normed = user_input.strip().lower()
    # Try active language first, then English as fallback
    result = GENRE_LOOKUP.get(_lang, {}).get(normed)
    if result is None:
        result = GENRE_LOOKUP["en"].get(normed)
    return result


# ---------------------------------------------------------------------------
# All UI strings
# ---------------------------------------------------------------------------
STRINGS: dict[str, dict[str, str]] = {
    # ==== ENGLISH ====
    "en": {
        # Language selection (always bilingual)
        "lang_prompt":      "Choose your language / 选择语言:",
        "lang_option_1":    "  1 = English",
        "lang_option_2":    "  2 = 中文",
        "lang_input":       "Enter 1 or 2 / 输入 1 或 2: ",
        "lang_invalid":     "Please enter 1 or 2. / 请输入 1 或 2。",

        # Welcome
        "welcome": "Hey there! I'm BookBot, your personal book recommender. Let's find your next read!",

        # Genre prompts
        "genre_list":       "Pick your flavor(s): {genres}",
        "genre_prompt":     "What genres do you vibe with? (1-3, comma-separated): ",
        "genre_empty":      "Oops — you didn't type anything! Give me at least one genre.",
        "genre_count":      "Whoa there — I can handle 1 to 3 genres, no more, no less!",
        "genre_invalid":    "Hmm, I don't recognize: {invalid}",
        "genre_allowed":    "I only speak these genres: {genres}",
        "genre_dup":        "You listed the same genre twice — I like your enthusiasm, but let's keep them unique!",

        # Book prompts
        "book_prompt":      "Name 2-3 books you absolutely love (comma-separated): ",
        "book_empty":       "Oops — you didn't type anything! Tell me about some books you love.",
        "book_injection":   "Nice try, but that doesn't look like a book title to me!",
        "book_count":       "I need exactly 2 or 3 books, no more, no less!",
        "book_invalid":     "Hmm, these don't look like real titles: {bad}. Book titles should have actual words and be under {max_len} characters.",

        # Familiarity prompts
        "fam_header":       "How adventurous are you feeling today?",
        "fam_1":            "  1 = Play it safe",
        "fam_2":            "  2 = Mostly classics, maybe one wild card",
        "fam_3":            "  3 = Half-and-half — familiar + fresh",
        "fam_4":            "  4 = Surprise me!",
        "fam_prompt":       "Pick a number (1-4): ",
        "fam_empty":        "Oops, you left that blank! Just type a number from 1 to 4.",
        "fam_nan":          "That's not a number! I need a digit between 1 and 4.",
        "fam_range":        "I can only count to 4 on this one — pick 1, 2, 3, or 4.",

        # Recommendation display
        "rec_header":       "Ta-da! Here are your BookBot picks:",
        "searching":        "Rummaging through the shelves...",
        "retry_llm":        "Something went wrong with the LLM. Retrying...",
        "retry_parse":      "Could not parse LLM response. Retrying...",
        "retry_validate":   "Those recommendations didn't pass my quality check. One more try...",
        "fail_all":         "Sorry, BookBot couldn't generate valid recommendations right now.",
        "fail_later":       "Please try again later.",
        "more_prompt":      "\nWould you like more recommendations? (yes / no): ",
        "more_yes":         "\nGood choice! Let me dig up more...\n",
        "more_no":          "\nHappy reading! Come back any time you need a fresh stack :D",
        "more_invalid":     "Please type 'yes' or 'no'.",

        # Subscription
        "sub_tab":          "Subscribe",
        "sub_title":        "Book recommendations",
        "sub_desc":         "Get personalized book picks delivered to your inbox on your schedule.",
        "sub_email_label":  "Your email",
        "sub_email_placeholder": "you@example.com",
        "sub_email_invalid": "Please enter a valid email address.",
        "sub_freq_invalid": "Please choose a valid frequency (daily, weekly, or monthly).",
        "sub_submit":       "Subscribe",
        "sub_success":      "You're subscribed! Recommendations will be sent to {email}.",
        "sub_already":      "This email is already subscribed.",
    },

    # ==== CHINESE ====
    "zh": {
        # Language selection (always bilingual)
        "lang_prompt":      "Choose your language / 选择语言:",
        "lang_option_1":    "  1 = English",
        "lang_option_2":    "  2 = 中文",
        "lang_input":       "Enter 1 or 2 / 输入 1 或 2: ",
        "lang_invalid":     "Please enter 1 or 2. / 请输入 1 或 2。",

        # Welcome
        "welcome": "你好！我是 BookBot，你的私人荐书助手。一起来找下一本好书吧！",

        # Genre prompts
        "genre_list":       "可选类型：{genres}",
        "genre_prompt":     "你喜欢哪些类型？（1-3个，用逗号分隔）: ",
        "genre_empty":      "哎呀——你什么都没输入！请至少选一个类型。",
        "genre_count":      "我只能处理 1 到 3 个类型哦！",
        "genre_invalid":    "嗯，我不认识这些: {invalid}",
        "genre_allowed":    "目前支持的类型：{genres}",
        "genre_dup":        "你重复选了同一个类型——热情我理解，但请保持每个类型都不同哦！",

        # Book prompts
        "book_prompt":      "说出 2-3 本你超爱的书（用逗号分隔）: ",
        "book_empty":       "哎呀——你什么都没输入！告诉我你喜欢的书吧。",
        "book_injection":   "这看起来不太像书名哦！",
        "book_count":       "我需要 2 到 3 本书，不多不少！",
        "book_invalid":     "嗯，这些看起来不像真正的书名: {bad}。书名应包含实际文字且不超过 {max_len} 个字符。",

        # Familiarity prompts
        "fam_header":       "你偏向哪种推荐风格",
        "fam_1":            "  1 = 稳妥一点，经典和畅销书优先",
        "fam_2":            "  2 = 基本稳妥，偶尔来个冷门",
        "fam_3":            "  3 = 一半熟悉一半新鲜",
        "fam_4":            "  4 = 给我惊喜！来点意外的，冷门的，小众的，不常见的书",
        "fam_prompt":       "选一个数字（1-4）: ",
        "fam_empty":        "诶，你什么都没输入呀！请输入 1 到 4 之间的数字。",
        "fam_nan":          "哎呀，这不是数字嘛！请输入 1 到 4 之间的数字。",
        "fam_range":        "只能选 1、2、3 或 4 哦。",

        # Recommendation display
        "rec_header":       "当当当！这是我为你精选的书单：",
        "searching":        "马上就来！正在翻阅书架...",
        "retry_llm":        "LLM 出了点问题，正在重试...",
        "retry_parse":      "无法解析 LLM 的回复，正在重试...",
        "retry_validate":   "哎呀，这些推荐没通过质量检查，再试一次...",
        "fail_all":         "抱歉，我暂时无法生成有效的推荐。",
        "fail_later":       "请稍后再试。",
        "more_prompt":      "\n还想要更多推荐吗？（是 / 否）: ",
        "more_yes":         "\n好的！让我再找找...\n",
        "more_no":          "\n祝你阅读愉快！欢迎随时回来找我推荐新书 :D",
        "more_invalid":     "请输入'是'或'否'。",

        # Subscription
        "sub_tab":          "订阅",
        "sub_title":        "定期推荐",
        "sub_desc":         "按你选择的频率，精选好书发到你的邮箱。",
        "sub_email_label":  "你的邮箱",
        "sub_email_placeholder": "you@example.com",
        "sub_email_invalid": "请输入有效的邮箱地址。",
        "sub_freq_invalid": "请选择有效的频率（每天、每周或每月）。",
        "sub_submit":       "订阅",
        "sub_success":      "订阅成功！推荐将发送到 {email}。",
        "sub_already":      "这个邮箱已经订阅了。",
    },
}
