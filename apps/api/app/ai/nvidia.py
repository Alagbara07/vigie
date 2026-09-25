import json
import logging
import time
from typing import Any

import httpx

from app.ai.prompt import SYSTEM_PROMPT
from app.ai.request import AnalysisRequest
from app.domain.errors import AIProviderError, InvalidProposalError

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

PROVIDER_NAME = "nvidia"
_RETRYABLE_STATUS = {502, 503, 504}


class NvidiaAIProvider:
    """NVIDIA chat adapter. It returns a proposal and does not write domain rows."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._url = _chat_url(base_url)
        self._timeout = timeout_seconds
        self._transport = transport
        self.last_latency_ms: int | None = None

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def model(self) -> str:
        return self._model

    def analyze_message(self, request: AnalysisRequest) -> dict[str, Any]:
        logger.info("Analyzing with NVIDIA model %s", self._model)
        started = time.perf_counter()
        try:
            content = self._complete(request)
            proposal = _proposal_from_content(content)
        except (AIProviderError, InvalidProposalError):
            self.last_latency_ms = _elapsed_ms(started)
            logger.info("NVIDIA analysis failed model=%s latency_ms=%s", self._model, self.last_latency_ms)
            raise
        self.last_latency_ms = _elapsed_ms(started)
        logger.info("NVIDIA analysis finished model=%s latency_ms=%s", self._model, self.last_latency_ms)
        return proposal

    def _complete(self, request: AnalysisRequest) -> str:
        payload = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_content(request)},
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        response: httpx.Response | None = None
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport, follow_redirects=False) as client:
                for attempt in (1, 2):
                    response = client.post(self._url, json=payload, headers=headers)
                    if response.status_code in _RETRYABLE_STATUS and attempt == 1:
                        logger.warning("NVIDIA request failed category=http_5xx status=%s", response.status_code)
                        continue
                    break
        except httpx.TimeoutException as exc:
            logger.warning("NVIDIA request failed category=timeout")
            raise AIProviderError("The NVIDIA provider timed out.") from exc
        except httpx.HTTPError as exc:
            logger.warning("NVIDIA request failed category=transport")
            raise AIProviderError("The NVIDIA provider could not be reached.") from exc
        if response is None:
            raise AIProviderError("The NVIDIA provider could not be reached.")
        if response.status_code >= 500:
            logger.warning("NVIDIA request failed category=http_5xx status=%s", response.status_code)
            raise AIProviderError("The NVIDIA provider could not complete the analysis.")
        if response.status_code >= 400:
            logger.warning("NVIDIA request failed category=http_4xx status=%s", response.status_code)
            raise AIProviderError("The NVIDIA provider rejected the request.")
        return _message_content(response)


def _chat_url(base_url: str) -> str:
    root = base_url.strip().rstrip("/")
    if root.endswith("/chat/completions"):
        return root
    return f"{root}/chat/completions"


def _user_content(request: AnalysisRequest) -> str:
    return (
        f"Default currency: {request.default_currency}\n"
        "Interpret only this customer message. Leave due_at null.\n\n"
        f"{request.content}"
    )


def _message_content(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError as exc:
        logger.warning("NVIDIA request failed category=malformed_json")
        raise InvalidProposalError("The AI proposal was rejected because it is not valid JSON.") from exc
    choices = body.get("choices") if isinstance(body, dict) else None
    if not isinstance(choices, list) or not choices:
        logger.warning("NVIDIA request failed category=invalid_response")
        raise InvalidProposalError("The AI proposal was rejected because the provider response had no analysis.")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        logger.warning("NVIDIA request failed category=invalid_response")
        raise InvalidProposalError("The AI proposal was rejected because the provider response had no analysis.")
    return content


def _proposal_from_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("NVIDIA request failed category=malformed_json")
        raise InvalidProposalError("The AI proposal was rejected because it is not valid JSON.") from exc
    if not isinstance(value, dict):
        logger.warning("NVIDIA request failed category=invalid_response")
        raise InvalidProposalError("The AI proposal was rejected because it is not a JSON object.")
    return value


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
