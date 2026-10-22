"""Single gateway to the LLM for every LOKI feature (chat, diagnosis, rules, healing).

Any LiteLLM-compatible provider works (Gemini, OpenAI, Anthropic, Mistral, Groq, Bedrock,
a local Ollama/vLLM server, any OpenAI-compatible endpoint), resolved by
`config.resolve_ai_connection()`. Sibling-model fallbacks, for transient "high demand"
errors, only apply to LOKI's own bundled Gemini default: once the user configured `ai:`
or --model, exactly that connection is tried and nothing else, so LOKI never silently
switches to a provider they didn't ask for.
"""
import json
import re
from collections.abc import Callable, Iterator
from typing import Any
import litellm
from loki.config import is_ai_customized, resolve_ai_connection

litellm.suppress_debug_info = True

DEFAULT_FALLBACK_MODELS = (
    "gemini/gemini-flash-lite-latest",
    "gemini/gemini-3.6-flash",
    "gemini/gemini-3.5-flash-lite",
)
DEFAULT_TIMEOUT = 25
_TRANSIENT_MARKERS = ("503", "unavailable", "timeout")
_RATE_LIMIT_MARKERS = ("429", "ratelimiterror", "resource_exhausted", "quota exceeded", "exceeded your current quota")
_JSON_FENCE = re.compile(r"^```[\w-]*[ \t]*\n(.*?)\n?```$", re.DOTALL)
_JSON_BLOB = re.compile(r"\{[\s\S]*\}")
_RETRY_IN = re.compile(r"retry in\s+([0-9]+h)?([0-9]+m)?([0-9]+(?:\.[0-9]+)?s)?", re.IGNORECASE)
_PROVIDER_HINT = re.compile(
    r"\b(gemini|openai|anthropic|mistral|groq|bedrock|ollama|azure|cohere)\b",
    re.IGNORECASE,
)
_MODEL_HINT = re.compile(r"\b((?:gemini|gpt|claude|llama|mistral)[\w./-]*)\b", re.IGNORECASE)

Messages = list[dict[str, Any]]


def is_rate_limit_error(error: Exception | None) -> bool:
    """True when the failure looks like HTTP 429 / quota exhaustion."""
    if error is None:
        return False
    text = f"{type(error).__name__} {error}".lower()
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)


def _provider_message(raw: str) -> str | None:
    """Pull the provider's short `message` field out of an embedded JSON payload."""
    match = _JSON_BLOB.search(raw)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return " ".join(message.split())
    return None


def _compact_retry(message: str) -> str | None:
    match = _RETRY_IN.search(message)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    if hours:
        return f"retry in ~{hours}"
    if minutes:
        return f"retry in ~{minutes}"
    if seconds:
        return f"retry in ~{seconds.rstrip('s')}s"
    return None


def summarize_llm_error(error: Exception | None) -> str:
    """One-line, human-readable summary of a provider failure (no raw JSON payload)."""
    if error is None:
        return "Unknown LLM error"
    raw = str(error).strip() or type(error).__name__
    provider_msg = _provider_message(raw)
    text = provider_msg or " ".join(raw.split())
    # Drop a trailing JSON blob if the provider message extraction failed.
    if provider_msg is None:
        text = _JSON_BLOB.sub("", text).strip(" -:\n\t")
        text = " ".join(text.split()) or type(error).__name__

    type_name = type(error).__name__
    provider = None
    provider_match = _PROVIDER_HINT.search(f"{type_name} {raw}")
    if provider_match:
        provider = provider_match.group(1).capitalize()
        if provider.lower() == "openai":
            provider = "OpenAI"

    model = None
    model_match = _MODEL_HINT.search(raw)
    if model_match:
        model = model_match.group(1)

    if is_rate_limit_error(error):
        head = f"{provider} quota exceeded (429)" if provider else "Quota exceeded (429)"
        detail_bits: list[str] = []
        lower = text.lower()
        if "free" in lower and "tier" in lower:
            detail_bits.append("free-tier limit reached")
        elif "quota" in lower:
            detail_bits.append("quota limit reached")
        else:
            detail_bits.append(text[:120])
        if model:
            detail_bits.append(f"for {model}")
        retry = _compact_retry(text) or _compact_retry(raw)
        if retry:
            detail_bits.append(f"— {retry}")
        return f"{head}: {' '.join(detail_bits)}"

    # Missing / invalid API key
    lower_raw = raw.lower()
    if any(marker in lower_raw for marker in ("api key", "apikey", "authentication", "unauthorized", "401", "403")):
        head = f"{provider} authentication error" if provider else "Authentication error"
        return f"{head}: {text[:160]}"

    # Timeouts / connection issues
    if any(marker in lower_raw for marker in ("timeout", "timed out", "connection", "connecterror", "network")):
        head = f"{provider} connection error" if provider else "Connection error"
        short = text[:160] if text else type_name
        return f"{head}: {short}"

    head = f"{provider} error" if provider else type_name
    return f"{head}: {text[:160]}"


class LLMError(Exception):
    """Every connection attempt failed. `last_error` holds the final underlying cause."""

    def __init__(self, message: str, last_error: Exception | None = None, *, is_rate_limit: bool | None = None):
        super().__init__(message)
        self.last_error = last_error
        self.is_rate_limit = is_rate_limit_error(last_error) if is_rate_limit is None else is_rate_limit

    @classmethod
    def from_cause(cls, last_error: Exception | None) -> "LLMError":
        """Build an LLMError whose message is a concise summary of `last_error`."""
        return cls(summarize_llm_error(last_error), last_error)


class LLMUnavailableError(LLMError):
    """Every attempt failed with a transient provider error (overload, outage, timeout)."""


def connection_attempts(model: str | None = None) -> list[dict[str, Any]]:
    """LiteLLM kwargs to try in order: the resolved connection, plus Gemini siblings if it is the default."""
    base = resolve_ai_connection(model)
    if is_ai_customized(model):
        return [base]
    return [base] + [{**base, "model": m} for m in DEFAULT_FALLBACK_MODELS if m != base.get("model")]


def is_transient(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def extract_json(text: str | None) -> Any:
    """Parses a JSON reply, tolerating a single surrounding ``` / ```json markdown fence."""
    raw = (text or "").strip()
    fenced = _JSON_FENCE.match(raw)
    if fenced:
        raw = fenced.group(1).strip()
    return json.loads(raw)


def _as_messages(prompt: str | Messages) -> Messages:
    return [{"role": "user", "content": prompt}] if isinstance(prompt, str) else prompt


def complete(
    prompt: str | Messages,
    model: str | None = None,
    parse: Callable[[str], Any] | None = None,
    **options: Any,
) -> Any:
    """Returns the first successful completion (passed through `parse` if given).

    A `parse` exception counts as a failed attempt, so a malformed reply moves on to the
    next fallback model. Raises LLMError once every attempt has failed.
    """
    options = {"timeout": DEFAULT_TIMEOUT, "num_retries": 1, **options}
    last_error: Exception | None = None
    for kwargs in connection_attempts(model):
        try:
            response = litellm.completion(messages=_as_messages(prompt), **options, **kwargs)
            text = response.choices[0].message.content or ""
            return parse(text) if parse else text
        except Exception as e:
            last_error = e
    raise LLMError.from_cause(last_error)


def complete_json(
    prompt: str | Messages,
    model: str | None = None,
    validate: Callable[[Any], bool] | None = None,
    **options: Any,
) -> Any:
    """Like complete(), but returns parsed JSON; replies failing `validate` count as failed attempts."""

    def parse(text: str) -> Any:
        data = extract_json(text)
        if validate and not validate(data):
            raise ValueError("LLM reply did not match the expected JSON schema")
        return data

    return complete(prompt, model=model, parse=parse, temperature=options.pop("temperature", 0.1), **options)


def open_stream(messages: Messages, model: str | None = None, **options: Any) -> Iterator[str]:
    """Starts a streamed completion and blocks until its first text chunk arrives.

    Transient provider errors fall through to the next fallback model; any other error
    is raised right away as LLMError. Returns an iterator over all text chunks, first included.
    """
    options = {"timeout": DEFAULT_TIMEOUT, "num_retries": 1, **options}
    last_error: Exception | None = None
    for kwargs in connection_attempts(model):
        try:
            chunks = (
                chunk.choices[0].delta.content or ""
                for chunk in litellm.completion(messages=messages, stream=True, **options, **kwargs)
            )
            first = next((text for text in chunks if text), "")
        except Exception as e:
            if not is_transient(e):
                raise LLMError.from_cause(e) from e
            last_error = e
            continue
        return _prepend(first, chunks)
    raise LLMUnavailableError(summarize_llm_error(last_error), last_error)


def _prepend(first: str, rest: Iterator[str]) -> Iterator[str]:
    if first:
        yield first
    for text in rest:
        if text:
            yield text
