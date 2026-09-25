import logging

from sqlalchemy.engine.url import make_url

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.seed.demo import seed_demo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    logger.info("Seeding demo inbox using the configured database")
    session = get_sessionmaker()()
    try:
        created = seed_demo(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    logger.info(
        "Demo seed finished. new_conversations=%s database=%s",
        created,
        make_url(settings.database_url).database,
    )


if __name__ == "__main__":
    main()
