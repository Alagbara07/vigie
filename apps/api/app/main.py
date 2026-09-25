import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.actions import router as actions_router
from app.api.analysis import router as analysis_router
from app.api.dashboard import router as dashboard_router
from app.api.evaluations import router as evaluations_router
from app.api.health import router as health_router
from app.api.inbox import router as inbox_router
from app.api.signals import router as signals_router
from app.api.system import router as system_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="VIGIE", version="0.1.0")


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, (HTTPException, RequestValidationError)):
        raise exc
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(health_router, prefix="/api")
app.include_router(system_router)
app.include_router(inbox_router)
app.include_router(analysis_router)
app.include_router(evaluations_router)
app.include_router(signals_router)
app.include_router(actions_router)
app.include_router(dashboard_router)
