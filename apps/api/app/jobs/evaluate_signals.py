"""Open signals for commitments and requests that are now due.

Run this from the host scheduler. Example:

    python -m app.jobs.evaluate_signals

The API process does not start a worker for this. One business that fails
does not stop evaluation for the others.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models import Business
from app.services.evaluation import run_evaluation

logger = logging.getLogger(__name__)


def evaluate_businesses(session, *, now: datetime | None = None) -> int:
    moment = now or datetime.now(timezone.utc)
    businesses = session.scalars(select(Business.id)).all()
    evaluated = 0
    for business_id in businesses:
        try:
            run_evaluation(session, business_id, moment)
            evaluated += 1
        except Exception:
            logger.warning("Signal evaluation failed business=%s category=evaluation", business_id)
    return evaluated


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    session = get_sessionmaker()()
    try:
        evaluated = evaluate_businesses(session)
        logger.info("Signal evaluation finished businesses=%s", evaluated)
    finally:
        session.close()


if __name__ == "__main__":
    main()
