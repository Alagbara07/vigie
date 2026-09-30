"""Renew Microsoft Graph subscriptions before they expire.

Run this once a day from the host scheduler. Example:

    python -m app.jobs.renew_microsoft_subscriptions

The API process does not start a worker for this.
"""

import logging

from app.core.database import get_sessionmaker
from app.integrations.microsoft_push import renew_expiring_microsoft_subscriptions

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    session = get_sessionmaker()()
    try:
        renewed = renew_expiring_microsoft_subscriptions(session)
        logger.info("Microsoft subscription renewal finished count=%s", renewed)
    finally:
        session.close()


if __name__ == "__main__":
    main()
