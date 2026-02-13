"""SQLite database for BookBot subscriptions and recommendation history."""

import json
import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager

# ---------------------------------------------------------------------------
# Database path (lives next to the package, not inside it)
# ---------------------------------------------------------------------------
_DB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_DB_DIR, "bookbot.db")

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
_SCHEMA = """\
CREATE TABLE IF NOT EXISTS subscriptions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    email             TEXT    NOT NULL UNIQUE,
    language          TEXT    NOT NULL CHECK(language IN ('en', 'zh')),
    genres            TEXT    NOT NULL,   -- JSON array
    books             TEXT    NOT NULL,   -- JSON array
    familiarity       INTEGER NOT NULL CHECK(familiarity BETWEEN 1 AND 4),
    unsubscribe_token TEXT    NOT NULL UNIQUE,
    active            INTEGER NOT NULL DEFAULT 1,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recommendation_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(id),
    titles          TEXT    NOT NULL,   -- JSON array
    sent_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def _connect():
    """Yield a SQLite connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't already exist."""
    with _connect() as conn:
        conn.executescript(_SCHEMA)
    logging.info("Database initialised at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Subscription helpers
# ---------------------------------------------------------------------------
def add_subscription(
    email: str,
    language: str,
    genres: list[str],
    books: list[str],
    familiarity: int,
) -> str:
    """Insert a new subscription and return its unsubscribe token.

    If the email already exists and is active, raises ``ValueError``.
    If it exists but is inactive, reactivates it with the new preferences.
    """
    token = uuid.uuid4().hex
    with _connect() as conn:
        # Check for existing row
        row = conn.execute(
            "SELECT id, active FROM subscriptions WHERE email = ?", (email,)
        ).fetchone()

        if row:
            if row["active"]:
                raise ValueError("This email is already subscribed.")
            # Reactivate with updated preferences
            conn.execute(
                """\
                UPDATE subscriptions
                   SET language = ?, genres = ?, books = ?, familiarity = ?,
                       unsubscribe_token = ?, active = 1
                 WHERE id = ?""",
                (
                    language,
                    json.dumps(genres),
                    json.dumps(books),
                    familiarity,
                    token,
                    row["id"],
                ),
            )
            logging.info("Reactivated subscription for %s", email)
        else:
            conn.execute(
                """\
                INSERT INTO subscriptions
                    (email, language, genres, books, familiarity, unsubscribe_token)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (email, language, json.dumps(genres), json.dumps(books), familiarity, token),
            )
            logging.info("New subscription for %s", email)
    return token


def deactivate_subscription(token: str) -> bool:
    """Mark a subscription as inactive by its unsubscribe token.

    Returns True if a row was updated, False if the token was not found.
    """
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE subscriptions SET active = 0 WHERE unsubscribe_token = ? AND active = 1",
            (token,),
        )
        if cur.rowcount:
            logging.info("Unsubscribed token=%s", token)
            return True
    return False


def get_active_subscriptions() -> list[dict]:
    """Return all active subscriptions as plain dicts."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM subscriptions WHERE active = 1"
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["genres"] = json.loads(d["genres"])
        d["books"] = json.loads(d["books"])
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# Recommendation history helpers
# ---------------------------------------------------------------------------
def get_recommended_titles(subscription_id: int) -> list[str]:
    """Return all previously recommended titles for a subscription."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT titles FROM recommendation_history WHERE subscription_id = ?",
            (subscription_id,),
        ).fetchall()
    titles: list[str] = []
    for row in rows:
        titles.extend(json.loads(row["titles"]))
    return titles


def add_history(subscription_id: int, titles: list[str]) -> None:
    """Record a batch of recommended titles for a subscription."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO recommendation_history (subscription_id, titles) VALUES (?, ?)",
            (subscription_id, json.dumps(titles)),
        )
    logging.info(
        "Recorded %d titles for subscription %d", len(titles), subscription_id
    )
