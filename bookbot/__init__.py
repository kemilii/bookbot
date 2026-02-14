"""BookBot — your personal AI book recommender."""

import logging
import os
import sys

_handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

# Also log to a file when running locally (not on Fly.io)
if not os.environ.get("FLY_APP_NAME"):
    _handlers.append(logging.FileHandler("bookbot.log"))

logging.basicConfig(
    handlers=_handlers,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
