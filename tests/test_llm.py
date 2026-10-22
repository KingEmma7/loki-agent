from types import SimpleNamespace
import pytest
from loki.ai import llm


def _reply(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _stream(*texts):
    return iter(SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=t))]) for t in texts)


@pytest.fixture
def default_connection(monkeypatch):
    """LOKI's bundled default: fallbacks enabled."""
    monkeypatch.setattr(llm, "is_ai_customized", lambda model: False)
    monkeypatch.setattr(llm, "resolve_ai_connection", lambda model: {"model": "gemini/gemini-flash-latest"})


@pytest.fixture
def custom_connection(monkeypatch):
    """User-configured provider: exactly one attempt, never a silent provider switch."""
    monkeypatch.setattr(llm, "is_ai_customized", lambda model: True)
    monkeypatch.setattr(llm, "resolve_ai_connection", lambda model: {"model": "ollama/llama3", "api_base": "http://localhost:11434"})


def _fake_completion(monkeypatch, outcomes):
    """Each call pops the next outcome: an Exception is raised, anything else is returned."""
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(llm.litellm, "completion", fake)
    return calls


def test_default_connection_tries_gemini_siblings(default_connection):
    models = [a["model"] for a in llm.connection_attempts()]
    assert models[0] == "gemini/gemini-flash-latest"
    assert models[1:] == list(llm.DEFAULT_FALLBACK_MODELS)


def test_custom_connection_never_falls_back(custom_connection, monkeypatch):
    calls = _fake_completion(monkeypatch, [RuntimeError("503 unavailable")])
    with pytest.raises(llm.LLMError):
        llm.complete("hi")
    assert len(calls) == 1
    assert calls[0]["api_base"] == "http://localhost:11434"


def test_complete_falls_back_then_succeeds(default_connection, monkeypatch):
    calls = _fake_completion(monkeypatch, [RuntimeError("boom"), _reply("diagnosis")])
    assert llm.complete("hi") == "diagnosis"
    assert [c["model"] for c in calls] == ["gemini/gemini-flash-latest", llm.DEFAULT_FALLBACK_MODELS[0]]
    assert calls[0]["messages"] == [{"role": "user", "content": "hi"}]


def test_complete_error_carries_last_cause(default_connection, monkeypatch):
    errors = [RuntimeError(f"fail {i}") for i in range(4)]
    _fake_completion(monkeypatch, list(errors))
    with pytest.raises(llm.LLMError) as exc:
        llm.complete("hi")
    assert exc.value.last_error is errors[-1]


@pytest.mark.parametrize("text", [
    '[{"status": "PASSED"}]',
    '```json\n[{"status": "PASSED"}]\n```',
    '```\n[{"status": "PASSED"}]\n```',
])
def test_extract_json_tolerates_fences(text):
    assert llm.extract_json(text) == [{"status": "PASSED"}]


def test_extract_json_keeps_fences_inside_values():
    text = '{"original_snippet": "```js\\ncode\\n```"}'
    assert llm.extract_json(text)["original_snippet"] == "```js\ncode\n```"


def test_complete_json_retries_on_invalid_reply(default_connection, monkeypatch):
    calls = _fake_completion(monkeypatch, [_reply("not json"), _reply('{"a": 1}'), _reply('[1]')])
    assert llm.complete_json("hi", validate=lambda d: isinstance(d, list)) == [1]
    assert len(calls) == 3
    assert all(c["temperature"] == 0.1 for c in calls)


def test_open_stream_yields_all_chunks(default_connection, monkeypatch):
    _fake_completion(monkeypatch, [_stream("", "Hel", None, "lo")])
    assert "".join(llm.open_stream([{"role": "user", "content": "hi"}])) == "Hello"


def test_open_stream_skips_transient_errors(default_connection, monkeypatch):
    calls = _fake_completion(monkeypatch, [RuntimeError("503 Service Unavailable"), _stream("ok")])
    assert list(llm.open_stream([])) == ["ok"]
    assert len(calls) == 2


def test_open_stream_stops_on_fatal_error(default_connection, monkeypatch):
    calls = _fake_completion(monkeypatch, [RuntimeError("401 invalid api key")])
    with pytest.raises(llm.LLMError) as exc:
        llm.open_stream([])
    assert not isinstance(exc.value, llm.LLMUnavailableError)
    assert len(calls) == 1


def test_open_stream_all_transient_is_unavailable(default_connection, monkeypatch):
    _fake_completion(monkeypatch, [RuntimeError("timeout")] * 4)
    with pytest.raises(llm.LLMUnavailableError):
        llm.open_stream([])


def test_summarize_rate_limit_strips_json_payload():
    raw = (
        'litellm.RateLimitError: litellm.RateLimitError: geminiException - {\n'
        '  "error": {\n'
        '    "code": 429,\n'
        '    "message": "You exceeded your current quota for gemini-3.8-flash. '
        'Please retry in 6h22m8.9s.",\n'
        '    "status": "RESOURCE_EXHAUSTED",\n'
        '    "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure"}]\n'
        "  }\n"
        "}"
    )
    err = type("RateLimitError", (Exception,), {})(raw)
    summary = llm.summarize_llm_error(err)
    assert "429" in summary
    assert "{" not in summary
    assert "RESOURCE_EXHAUSTED" not in summary
    assert "retry in ~6h" in summary
    assert llm.is_rate_limit_error(err) is True


def test_summarize_missing_api_key():
    err = RuntimeError("401 invalid api key for openai")
    summary = llm.summarize_llm_error(err)
    assert "Authentication" in summary or "authentication" in summary.lower()
    assert "{" not in summary
    assert llm.is_rate_limit_error(err) is False


def test_summarize_timeout():
    err = TimeoutError("Request timed out after 25s connecting to api.example.com")
    summary = llm.summarize_llm_error(err)
    assert "Connection" in summary or "timeout" in summary.lower()
    assert "{" not in summary


def test_complete_raises_concise_llm_error(custom_connection, monkeypatch):
    raw = (
        'RateLimitError: geminiException - {"error": {"code": 429, '
        '"message": "You exceeded your current quota. Please retry in 1h5m", '
        '"status": "RESOURCE_EXHAUSTED"}}'
    )
    cause = type("RateLimitError", (Exception,), {})(raw)
    _fake_completion(monkeypatch, [cause])
    with pytest.raises(llm.LLMError) as exc:
        llm.complete("hi")
    assert exc.value.last_error is cause
    assert exc.value.is_rate_limit is True
    assert "{" not in str(exc.value)
    assert "429" in str(exc.value)
