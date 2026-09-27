"""Renew Gmail watches that are near the expiration Google returned.

Run this once a day from the host scheduler. Example:

    python -m app.jobs.renew_gmail_watches

The API process does not start a worker, queue, or cache for this.
"""

import logging

from app.core.database import get_sessionmaker
from app.integrations.gmail_push import renew_expiring_gmail_watches

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    session = get_sessionmaker()()
    try:
        renewed = renew_expiring_gmail_watches(session)
        logger.info("Gmail watch renewal finished count=%s", renewed)
    finally:
        session.close()


if __name__ == "__main__":
    main()
