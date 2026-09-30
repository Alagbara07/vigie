import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import Principal, require_admin, require_member
from app.auth.sessions import session_token, user_from_request_token
from app.core.config import get_settings
from app.core.database import get_db
from app.domain.enums import IntegrationProvider
from app.domain.errors import ConflictError, NotFoundError, ProviderError
from app.integrations.connections import begin_oauth, connect_whatsapp, disconnect, list_channels
from app.integrations.gmail import GmailAdapter, complete_gmail_oauth, sync_gmail
from app.integrations.gmail_push import receive_gmail_notification, register_gmail_watch
from app.integrations.pubsub_auth import verify_pubsub_push
from app.integrations.microsoft import MicrosoftAdapter, complete_microsoft_oauth, sync_microsoft
from app.integrations.microsoft_push import receive_microsoft_notification, register_microsoft_subscription, validation_token
from app.integrations.oauth_log import attempt_id, bind, new_request_id, prefix
from app.integrations.whatsapp import WhatsAppAdapter, receive_whatsapp_events
from app.schemas.channels import ChannelStatusRead, DisconnectRequest, SyncRead, WhatsAppConnectRequest
from app.services.audit import record_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/integrations", response_model=list[ChannelStatusRead])
def get_integrations(
    response: Response,
    business_id: uuid.UUID = Query(),
    principal: Principal = Depends(require_member),
    session: Session = Depends(get_db),
) -> list[dict]:
    del principal
    response.headers["Cache-Control"] = "no-store"
    try:
        return list_channels(session, business_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/integrations/whatsapp/connect", response_model=ChannelStatusRead)
def post_whatsapp_connect(
    payload: WhatsAppConnectRequest,
    principal: Principal = Depends(require_admin),
    session: Session = Depends(get_db),
) -> dict:
    try:
        connection = connect_whatsapp(
            session,
            payload.business_id,
            payload.phone_number_id,
            payload.display_name,
            user_id=principal.user.id,
        )
        record_audit(
            session,
            user_id=principal.user.id,
            business_id=payload.business_id,
            action="integration_connected",
            resource_type="integration",
            resource_id=str(connection.id),
            metadata={"provider": IntegrationProvider.WHATSAPP.value},
        )
    except ProviderError as exc:
        raise _provider_error(exc) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _one(session, payload.business_id, IntegrationProvider.WHATSAPP)


@router.get("/integrations/whatsapp/webhook")
def get_whatsapp_webhook(
    request: Request,
) -> PlainTextResponse:
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    try:
        verified = WhatsAppAdapter().verify_subscription(mode, token, challenge)
    except ProviderError as exc:
        raise HTTPException(status_code=403, detail="Webhook verification failed.") from exc
    return PlainTextResponse(verified)


@router.post("/integrations/whatsapp/webhook")
async def post_whatsapp_webhook(
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, int]:
    body = await request.body()
    adapter = WhatsAppAdapter()
    try:
        adapter.verify_signature(body, request.headers.get("x-hub-signature-256"))
        return receive_whatsapp_events(session, body)
    except ProviderError as exc:
        raise _provider_error(exc) from exc


@router.get("/integrations/gmail/connect")
def get_gmail_connect(
    business_id: uuid.UUID = Query(),
    principal: Principal = Depends(require_admin),
    session: Session = Depends(get_db),
) -> RedirectResponse:
    if business_id != principal.business_id:
        raise HTTPException(status_code=403, detail="You do not have access to this business.")
    if not get_settings().gmail_configured():
        raise HTTPException(status_code=409, detail="Configuration required.")
    try:
        state = begin_oauth(session, principal.business_id, IntegrationProvider.GMAIL, principal.user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProviderError as exc:
        raise _provider_error(exc) from exc
    return RedirectResponse(GmailAdapter().authorization_url(state), status_code=302)


@router.get("/integrations/gmail/callback")
def get_gmail_callback(
    request: Request,
    code: str = "",
    state: str = "",
    session: Session = Depends(get_db),
) -> RedirectResponse:
    return _finish_oauth(
        session,
        lambda: complete_gmail_oauth(session, code, state, _viewer_id(request, session)),
        "gmail",
    )


@router.post("/integrations/gmail/sync", response_model=SyncRead)
def post_gmail_sync(
    business_id: uuid.UUID = Query(),
    principal: Principal = Depends(require_admin),
    session: Session = Depends(get_db),
) -> dict[str, int]:
    if business_id != principal.business_id:
        raise HTTPException(status_code=403, detail="You do not have access to this business.")
    return _sync(lambda: sync_gmail(session, principal.business_id))


@router.post("/integrations/gmail/watch", response_model=ChannelStatusRead)
def post_gmail_watch(
    business_id: uuid.UUID = Query(),
    principal: Principal = Depends(require_admin),
    session: Session = Depends(get_db),
) -> dict:
    if business_id != principal.business_id:
        raise HTTPException(status_code=403, detail="You do not have access to this business.")
    try:
        register_gmail_watch(session, principal.business_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProviderError as exc:
        raise _pubsub_error(exc) from exc
    return _one(session, principal.business_id, IntegrationProvider.GMAIL)


@router.post("/integrations/gmail/pubsub")
async def post_gmail_pubsub(request: Request, session: Session = Depends(get_db)) -> dict[str, int]:
    body = await request.body()
    try:
        verify_pubsub_push(request.headers.get("authorization"))
        return receive_gmail_notification(session, body)
    except ProviderError as exc:
        raise _pubsub_error(exc) from exc


@router.get("/integrations/microsoft/connect")
def get_microsoft_connect(
    business_id: uuid.UUID = Query(),
    principal: Principal = Depends(require_admin),
    session: Session = Depends(get_db),
) -> RedirectResponse:
    if business_id != principal.business_id:
        raise HTTPException(status_code=403, detail="You do not have access to this business.")
    settings = get_settings()
    if not settings.microsoft_configured():
        raise HTTPException(status_code=409, detail="Configuration required.")
    try:
        state = begin_oauth(session, principal.business_id, IntegrationProvider.MICROSOFT365, principal.user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProviderError as exc:
        raise _provider_error(exc) from exc
    bind(new_request_id(), attempt_id(state))
    redirect_uri = settings.resolved_microsoft_redirect_uri()
    logger.info(
        "%sMicrosoft OAuth initiated business=%s user=%s redirect=%s tenant=%s path_ok=%s trailing_slash=%s",
        prefix(),
        principal.business_id,
        principal.user.id,
        redirect_uri,
        settings.microsoft_tenant_id.strip() or "common",
        redirect_uri.endswith("/api/integrations/microsoft/callback"),
        redirect_uri.endswith("/"),
    )
    return RedirectResponse(MicrosoftAdapter().authorization_url(state), status_code=302)


@router.get("/integrations/microsoft/callback")
def get_microsoft_callback(
    request: Request,
    code: str = "",
    state: str = "",
    session: Session = Depends(get_db),
) -> RedirectResponse:
    bind(new_request_id(), attempt_id(state))
    provider_error_present = bool(_safe_oauth_error(request.query_params.get("error")))
    logger.info(
        "%sMicrosoft OAuth callback received code_present=%s state_present=%s provider_error=%s tenant=%s",
        prefix(),
        bool(code.strip()),
        bool(state.strip()),
        provider_error_present,
        get_settings().microsoft_tenant_id.strip() or "common",
    )
    provider_error = _safe_oauth_error(request.query_params.get("error"))
    if provider_error:
        reason = _microsoft_provider_reason(provider_error, request.query_params.get("error_subcode"))
        logger.warning(
            "%sMicrosoft OAuth callback rejected category=provider code=%s reason=%s",
            prefix(),
            provider_error,
            reason,
        )
        return _oauth_error_redirect("microsoft365", reason)
    return _finish_oauth(
        session,
        lambda: complete_microsoft_oauth(session, code, state, _viewer_id(request, session)),
        "microsoft365",
    )


@router.get("/integrations/microsoft/webhook")
async def microsoft_webhook_validation(request: Request, session: Session = Depends(get_db)) -> Response:
    return await _microsoft_webhook(request, session)


@router.post("/integrations/microsoft/webhook")
async def microsoft_webhook(request: Request, session: Session = Depends(get_db)) -> Response:
    return await _microsoft_webhook(request, session)


async def _microsoft_webhook(request: Request, session: Session) -> Response:
    presented = request.query_params.get("validationToken")
    if presented is not None:
        try:
            token = validation_token(presented)
        except ProviderError as exc:
            raise HTTPException(status_code=400, detail="The Microsoft notification is not valid.") from exc
        return PlainTextResponse(token, status_code=200)
    if request.method != "POST":
        raise HTTPException(status_code=400, detail="The Microsoft notification is not valid.")
    body = await request.body()
    try:
        receive_microsoft_notification(session, body)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail="The Microsoft notification is not valid.") from exc
    return Response(status_code=202)


@router.post("/integrations/microsoft/watch", response_model=ChannelStatusRead)
def post_microsoft_watch(
    business_id: uuid.UUID = Query(),
    principal: Principal = Depends(require_admin),
    session: Session = Depends(get_db),
) -> dict:
    if business_id != principal.business_id:
        raise HTTPException(status_code=403, detail="You do not have access to this business.")
    try:
        register_microsoft_subscription(session, principal.business_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProviderError as exc:
        raise _provider_error(exc) from exc
    return _one(session, principal.business_id, IntegrationProvider.MICROSOFT365)


@router.post("/integrations/microsoft/sync", response_model=SyncRead)
def post_microsoft_sync(
    business_id: uuid.UUID = Query(),
    principal: Principal = Depends(require_admin),
    session: Session = Depends(get_db),
) -> dict[str, int]:
    del principal
    return _sync(lambda: sync_microsoft(session, business_id))


@router.post("/integrations/{provider}/disconnect", response_model=ChannelStatusRead)
def post_disconnect(
    provider: IntegrationProvider,
    payload: DisconnectRequest,
    principal: Principal = Depends(require_admin),
    session: Session = Depends(get_db),
) -> dict:
    if provider is IntegrationProvider.DEMO:
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        disconnect(session, payload.business_id, provider)
        record_audit(
            session,
            user_id=principal.user.id,
            business_id=payload.business_id,
            action="integration_disconnected",
            resource_type="integration",
            resource_id=provider.value,
            metadata={"provider": provider.value},
        )
    except ProviderError as exc:
        raise _provider_error(exc) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _one(session, payload.business_id, provider)


def _one(session: Session, business_id: uuid.UUID, provider: IntegrationProvider) -> dict:
    for item in list_channels(session, business_id):
        if item["provider"] == provider.value:
            return item
    raise HTTPException(status_code=404, detail="Not found.")


def _finish_oauth(session: Session, complete, provider: str) -> RedirectResponse:
    try:
        complete()
    except (ProviderError, NotFoundError, ConflictError) as exc:
        reason = exc.reason if isinstance(exc, ProviderError) else None
        logger.warning("OAuth callback failed provider=%s result=error reason=%s", provider, reason or "unspecified")
        return _oauth_error_redirect(provider, reason if provider == "microsoft365" else None)
    logger.info("OAuth callback completed provider=%s result=connected", provider)
    return _oauth_redirect(provider, f"connection={provider}")


_OAUTH_REASONS = {"cancelled", "incomplete", "permissions", "verify", "finish"}


def _oauth_error_redirect(provider: str, reason: str | None) -> RedirectResponse:
    query = f"connection=error&provider={provider}"
    if reason in _OAUTH_REASONS:
        query = f"{query}&reason={reason}"
    if provider == "microsoft365":
        logger.warning("%sMicrosoft OAuth result=failure category=%s", prefix(), reason or "unspecified")
    logger.info("%sOAuth redirect provider=%s destination=/settings/integrations?%s", prefix(), provider, query)
    target = get_settings().public_web_url.rstrip("/") + "/settings/integrations"
    return RedirectResponse(f"{target}?{query}", status_code=302)


def _oauth_redirect(provider: str, query: str) -> RedirectResponse:
    if provider == "microsoft365":
        logger.info("%sMicrosoft OAuth result=success category=connected", prefix())
    logger.info("%sOAuth redirect provider=%s destination=/settings/integrations?%s", prefix(), provider, query)
    target = get_settings().public_web_url.rstrip("/") + "/settings/integrations"
    return RedirectResponse(f"{target}?{query}", status_code=302)


def _microsoft_provider_reason(code: str, subcode: object) -> str:
    sub = subcode.strip().lower() if isinstance(subcode, str) else ""
    if code == "access_denied" and sub == "cancel":
        return "cancelled"
    if code in {"access_denied", "consent_required", "interaction_required"}:
        return "permissions"
    return "incomplete"


def _sync(operation):
    try:
        return operation()
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProviderError as exc:
        raise _provider_error(exc) from exc


def _safe_oauth_error(value: object) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if not cleaned:
        return ""
    if cleaned.isascii() and " " not in cleaned and 1 <= len(cleaned) <= 80:
        return cleaned
    return "unknown"


def _viewer_id(request: Request, session: Session) -> uuid.UUID | None:
    user = user_from_request_token(session, session_token(request.cookies))
    return None if user is None else user.id


def _pubsub_error(exc: ProviderError) -> HTTPException:
    message = str(exc)
    if message == "Pub/Sub authentication failed.":
        return HTTPException(status_code=401, detail=message)
    if message == "Pub/Sub is not configured.":
        return HTTPException(status_code=403, detail=message)
    if message == "The Pub/Sub payload is not valid.":
        return HTTPException(status_code=400, detail=message)
    if message == "Real-time listening is not configured.":
        return HTTPException(status_code=409, detail=message)
    if message in {"VIGIE could not sync Gmail.", "Real-time listening could not be enabled."}:
        return HTTPException(status_code=503, detail=message)
    return HTTPException(status_code=409, detail="VIGIE could not sync Gmail.")


def _provider_error(exc: ProviderError) -> HTTPException:
    message = str(exc)
    if message in {"Invalid signature.", "Webhook verification failed.", "Configuration required."}:
        status = 403 if message != "Configuration required." else 409
        if message == "Webhook verification failed.":
            status = 403
        return HTTPException(status_code=status, detail=message)
    if message == "The webhook payload is not valid JSON.":
        return HTTPException(status_code=400, detail=message)
    if message == "Invalid or expired connection attempt.":
        return HTTPException(status_code=400, detail=message)
    return HTTPException(status_code=409, detail=message)
