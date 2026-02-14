"""APScheduler-based job for sending book recommendations.

Runs once per day and dispatches to subscribers whose chosen frequency
(daily, weekly, monthly) matches the current date.
"""

import datetime
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from bookbot.database import (
    get_active_subscriptions,
    get_recommended_titles,
    add_history,
)
from bookbot.i18n import set_language
from bookbot.mailer import send_recommendations_email
from bookbot.recommender import (
    get_system_prompt,
    build_user_prompt,
    call_llm,
    parse_llm_output,
    validate_recommendations,
)

# ---------------------------------------------------------------------------
# The recommendation job
# ---------------------------------------------------------------------------
MAX_ATTEMPTS = 3


def _generate_for_subscriber(sub: dict) -> list[dict] | None:
    """Generate recommendations for a single subscriber.

    Returns a list of recommendation dicts, or None on failure.
    """
    set_language(sub["language"])

    prefs = {
        "genres": sub["genres"],
        "favorite_books": sub["books"],
        "familiarity_level": sub["familiarity"],
    }

    exclude = get_recommended_titles(sub["id"])
    user_prompt = build_user_prompt(prefs, exclude=exclude or None)
    system_prompt = get_system_prompt()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw = call_llm(system_prompt, user_prompt)
        if raw is None:
            logging.warning(
                "LLM returned None for subscriber %d, attempt %d", sub["id"], attempt
            )
            continue

        parsed = parse_llm_output(raw)
        if parsed is None:
            logging.warning(
                "Parse failed for subscriber %d, attempt %d", sub["id"], attempt
            )
            continue

        final = validate_recommendations(parsed, prefs)
        if final is None:
            logging.warning(
                "Validation failed for subscriber %d, attempt %d", sub["id"], attempt
            )
            continue

        # Remove already-sent titles
        if exclude:
            seen = {t.strip().lower() for t in exclude}
            final = [r for r in final if r["title"].strip().lower() not in seen]

        if final:
            return final

    logging.error("All attempts failed for subscriber %d", sub["id"])
    return None


def _should_send_today(frequency: str, today: datetime.date | None = None) -> bool:
    """Return True if a subscriber with the given frequency should receive
    recommendations today.

    - ``daily``  : every day
    - ``weekly`` : every Monday
    - ``monthly``: the 1st of each month
    """
    if today is None:
        today = datetime.date.today()

    if frequency == "daily":
        return True
    if frequency == "weekly":
        return today.weekday() == 0  # Monday
    if frequency == "monthly":
        return today.day == 1
    return False


def send_scheduled_recommendations() -> None:
    """Iterate over all active subscribers and email those whose frequency
    matches today's date."""
    today = datetime.date.today()
    subscribers = get_active_subscriptions()
    logging.info(
        "Daily scheduler job started (%s) — %d active subscriber(s)",
        today.isoformat(),
        len(subscribers),
    )

    sent_count = 0
    for sub in subscribers:
        freq = sub.get("frequency", "monthly")
        if not _should_send_today(freq, today):
            continue

        logging.info(
            "Processing subscriber %d (%s, frequency=%s)", sub["id"], sub["email"], freq
        )

        recs = _generate_for_subscriber(sub)
        if recs is None:
            logging.error("Skipping subscriber %d — no recommendations generated", sub["id"])
            continue

        sent = send_recommendations_email(
            to_email=sub["email"],
            recs=recs,
            language=sub["language"],
            unsubscribe_token=sub["unsubscribe_token"],
        )

        if sent:
            titles = [r["title"] for r in recs]
            add_history(sub["id"], titles)
            sent_count += 1

    logging.info("Scheduler job finished — sent to %d subscriber(s).", sent_count)


# Keep the old name as an alias for backwards compatibility
send_monthly_recommendations = send_scheduled_recommendations


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------
_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    """Start the background scheduler with a daily job at 09:00 UTC.

    The job checks each subscriber's chosen frequency to decide whether
    to send recommendations on a given day.

    Safe to call multiple times — only the first call has effect.
    """
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(daemon=True)
    # Run every day at 09:00 UTC
    _scheduler.add_job(
        send_scheduled_recommendations,
        trigger="cron",
        hour=9,
        minute=0,
        id="scheduled_recommendations",
        replace_existing=True,
    )
    _scheduler.start()
    logging.info("Scheduler started — daily job registered at 09:00 UTC")


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logging.info("Scheduler stopped.")
