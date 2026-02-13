"""APScheduler-based monthly job for sending book recommendations."""

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
# The monthly job
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


def send_monthly_recommendations() -> None:
    """Iterate over all active subscribers, generate recs, and email them."""
    subscribers = get_active_subscriptions()
    logging.info("Monthly job started — %d active subscriber(s)", len(subscribers))

    for sub in subscribers:
        logging.info("Processing subscriber %d (%s)", sub["id"], sub["email"])

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

    logging.info("Monthly job finished.")


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------
_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    """Start the background scheduler with the monthly job.

    Safe to call multiple times — only the first call has effect.
    """
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(daemon=True)
    # TEST MODE: Run every 1 minutes
    # TODO: Revert to monthly before deploying:
    #   trigger="cron", day=1, hour=9, minute=0
    _scheduler.add_job(
        send_monthly_recommendations,
        trigger="interval",
        minutes=1,
        id="monthly_recommendations",
        replace_existing=True,
    )
    _scheduler.start()
    logging.info("Scheduler started — job running every 1 minute (TEST MODE)")


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logging.info("Scheduler stopped.")
