import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.actions import router as actions_router
from app.api.auth import router as auth_router
from app.api.channels import router as channels_router
from app.api.analysis import router as analysis_router
from app.api.dashboard import router as dashboard_router
from app.api.demo import router as demo_router
from app.api.evaluations import router as evaluations_router
from app.api.health import router as health_router
from app.api.inbox import router as inbox_router
from app.api.integrations import router as integrations_router
from app.api.signals import router as signals_router
from app.api.system import router as system_router
from app.auth.cookies import SESSION_COOKIE
from app.auth.deps import reject_cross_site

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="VIGIE", version="0.1.0")


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.cookies.get(SESSION_COOKIE):
        try:
            reject_cross_site(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, (HTTPException, RequestValidationError)):
        raise exc
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(health_router, prefix="/api")
app.include_router(auth_router)
app.include_router(system_router)
app.include_router(inbox_router)
app.include_router(analysis_router)
app.include_router(evaluations_router)
app.include_router(signals_router)
app.include_router(actions_router)
app.include_router(dashboard_router)
app.include_router(demo_router)
app.include_router(integrations_router)
app.include_router(channels_router)
