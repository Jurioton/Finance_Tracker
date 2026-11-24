"""Small client for a local Ollama server (https://ollama.com).

All AI in the app runs on the user's own computer through Ollama: auto-categorize, monthly insights
and the assistant chat. Nothing is sent to a cloud service.

Ollama's HTTP API is simple enough that we call it directly with httpx instead of adding a library.
"""
import json
import logging
import time
from collections.abc import Iterator

import httpx

from . import config

log = logging.getLogger(__name__)


class OllamaError(Exception):
    """Something went wrong talking to Ollama. `str(error)` is a message we can show to the user."""


class OllamaUnavailable(OllamaError):
    pass


class ModelMissing(OllamaError):
    pass


class ToolsUnsupported(OllamaError):
    pass


def _url(path: str) -> str:
    return config.OLLAMA_URL.rstrip("/") + path


def _model_matches(name: str, wanted: str) -> bool:
    # "llama3.2" is stored by Ollama as "llama3.2:latest"
    return name == wanted or name == f"{wanted}:latest" or (":" not in wanted and name.split(":")[0] == wanted)


def unavailable_message() -> str:
    return (f"The local AI isn't running. Start Ollama (open the Ollama app, or run `ollama serve`) "
            f"and make sure it's reachable at {config.OLLAMA_URL}.")


def missing_model_message() -> str:
    return (f"The AI model \"{config.OLLAMA_MODEL}\" isn't downloaded yet. "
            f"Run `ollama pull {config.OLLAMA_MODEL}` in a terminal, then try again.")


def status(timeout: float = 2.0) -> dict:
    """Checks whether Ollama is running and the configured model is downloaded."""
    base = {"model": config.OLLAMA_MODEL, "url": config.OLLAMA_URL}
    if not config.AI_ENABLED:
        return {**base, "available": False, "model_installed": False,
                "message": "AI features are turned off (AI_ENABLED=false)."}
    try:
        res = httpx.get(_url("/api/tags"), timeout=timeout)
        res.raise_for_status()
        names = [m.get("name", "") for m in res.json().get("models", [])]
    except (httpx.HTTPError, ValueError):
        return {**base, "available": False, "model_installed": False, "message": unavailable_message()}
    installed = any(_model_matches(n, config.OLLAMA_MODEL) for n in names)
    return {**base, "available": True, "model_installed": installed,
            "message": None if installed else missing_model_message()}


# Auto-categorize runs on every keystroke pause, so remember the last status check for a short while
# instead of asking Ollama each time (and waiting on a timeout when it's not running).
_ready_cache: tuple[float, bool] = (0.0, False)
READY_CACHE_SECONDS = 30


def is_ready() -> bool:
    global _ready_cache
    checked_at, ready = _ready_cache
    if time.monotonic() - checked_at < READY_CACHE_SECONDS:
        return ready
    s = status(timeout=1.0)
    ready = s["available"] and s["model_installed"]
    _ready_cache = (time.monotonic(), ready)
    return ready


def _raise_for_response(res: httpx.Response) -> None:
    if res.status_code < 400:
        return
    try:
        res.read()
        detail = res.json().get("error", res.text)
    except Exception:
        detail = f"HTTP {res.status_code}"
    text = str(detail).lower()
    if res.status_code == 404 or "not found" in text:
        raise ModelMissing(missing_model_message())
    if "does not support tools" in text:
        raise ToolsUnsupported(str(detail))
    raise OllamaError(f"The local AI returned an error: {detail}")


def _payload(messages: list[dict], tools: list[dict] | None, format: dict | None, stream: bool) -> dict:
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": messages,
        "stream": stream,
        "options": {"temperature": 0.2, "num_ctx": config.OLLAMA_NUM_CTX},
    }
    if tools:
        payload["tools"] = tools
    if format:
        payload["format"] = format
    return payload


def _timeout() -> httpx.Timeout:
    # Loading a model into memory the first time can take a while, so the read timeout is generous
    return httpx.Timeout(config.OLLAMA_TIMEOUT, connect=5.0)


def chat(messages: list[dict], format: dict | None = None, tools: list[dict] | None = None) -> dict:
    """One non-streaming chat request. Returns Ollama's `message` dict."""
    try:
        res = httpx.post(_url("/api/chat"), json=_payload(messages, tools, format, False), timeout=_timeout())
    except httpx.ConnectError as exc:
        raise OllamaUnavailable(unavailable_message()) from exc
    except httpx.TimeoutException as exc:
        raise OllamaError("The local AI took too long to answer. Try again in a moment.") from exc
    except httpx.HTTPError as exc:
        raise OllamaError(f"Couldn't talk to the local AI: {exc}") from exc
    _raise_for_response(res)
    return res.json().get("message", {})


def chat_stream(messages: list[dict], tools: list[dict] | None = None) -> Iterator[dict]:
    """Streams a chat reply. Yields Ollama's `message` chunks, e.g. {"content": "Hel"} or {"tool_calls": [...]}."""
    try:
        with httpx.stream("POST", _url("/api/chat"), json=_payload(messages, tools, None, True),
                          timeout=_timeout()) as res:
            _raise_for_response(res)
            for line in res.iter_lines():
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if chunk.get("error"):
                    raise OllamaError(f"The local AI returned an error: {chunk['error']}")
                if chunk.get("message"):
                    yield chunk["message"]
                if chunk.get("done"):
                    return
    except httpx.ConnectError as exc:
        raise OllamaUnavailable(unavailable_message()) from exc
    except httpx.TimeoutException as exc:
        raise OllamaError("The local AI took too long to answer. Try again in a moment.") from exc
    except httpx.HTTPError as exc:
        raise OllamaError(f"Couldn't talk to the local AI: {exc}") from exc
