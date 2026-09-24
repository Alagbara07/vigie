import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.database import get_engine

logger = logging.getLogger(__name__)

router = APIRouter()

DATABASE_OK = "ok"
DATABASE_UNAVAILABLE = "unavailable"


def check_database(engine: Engine) -> str:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        logger.exception("PostgreSQL health check failed")
        return DATABASE_UNAVAILABLE
    return DATABASE_OK


def build_health_response(database: str) -> JSONResponse:
    database_ready = database == DATABASE_OK
    return JSONResponse(
        status_code=200 if database_ready else 503,
        content={
            "status": "ok" if database_ready else "degraded",
            "service": "vigie-api",
            "api": "ok",
            "database": DATABASE_OK if database_ready else DATABASE_UNAVAILABLE,
        },
    )


@router.get("/health")
def health() -> JSONResponse:
    database = check_database(get_engine())
    return build_health_response(database)
