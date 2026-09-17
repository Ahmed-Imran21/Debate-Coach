"""
The response_format passthrough on APIClient.generate must be
inert for every existing caller (default None) and must map to
each provider's native JSON mode when asked for.

Provider tests stub the SDK client. The gateway test builds a
real APIClient against fake env keys and stubs the provider
adapters, so scheduling and reservation run for real while no
network call is made.
"""

from types import SimpleNamespace
from typing import Any

import pytest

from api.models import APIKey, APILimits


def _fake_key(provider: str, model: str) -> APIKey:
    return APIKey(
        id=f"{provider}_test",
        provider=provider,
        model=model,
        key="fake",
        limits=APILimits(rpm=100, rpd=1000, tpm=100000, tpd=1000000),
    )


# ---------------------------------------------------------------
# Provider adapters
# ---------------------------------------------------------------

class _Recorder:
    def __init__(self) -> None:
        self.kwargs: dict = {}


def test_groq_provider_omits_response_format_by_default(monkeypatch):
    from api.providers import groq as groq_module

    rec = _Recorder()

    class FakeCompletions:
        def create(self, **kwargs: Any):
            rec.kwargs = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="{}"), finish_reason="stop")],
                usage=None,
            )

    class FakeGroq:
        def __init__(self, api_key: str) -> None:
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(groq_module, "Groq", FakeGroq)

    provider = groq_module.GroqProvider()
    provider.generate(_fake_key("groq", "m"), messages=[{"role": "user", "content": "hi"}])
    assert "response_format" not in rec.kwargs

    provider.generate(
        _fake_key("groq", "m"),
        messages=[{"role": "user", "content": "Return JSON."}],
        json_mode=True,
    )
    assert rec.kwargs["response_format"] == {"type": "json_object"}


def test_gemini_provider_sets_mime_type_only_when_asked(monkeypatch):
    from api.providers import gemini as gemini_module

    rec = _Recorder()

    class FakeModels:
        def generate_content(self, **kwargs: Any):
            rec.kwargs = kwargs
            return SimpleNamespace(text="{}", usage_metadata=None, candidates=[])

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            self.models = FakeModels()

    monkeypatch.setattr(gemini_module.genai, "Client", FakeClient)

    provider = gemini_module.GeminiProvider()
    provider.generate(_fake_key("gemini", "m"), prompt="hi", temperature=0.1)
    assert rec.kwargs["config"] == {"temperature": 0.1}

    provider.generate(_fake_key("gemini", "m"), prompt="Return JSON.", json_mode=True)
    assert rec.kwargs["config"]["response_mime_type"] == "application/json"


# ---------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------

@pytest.fixture
def api_client(monkeypatch):
    # One fake key per provider so build_registry() succeeds and the
    # scheduler has something to reserve against.
    monkeypatch.setenv("GROQ_GPT_OSS_120B_KEY_1", "fake-groq")
    monkeypatch.setenv("GEMINI_2_5_FLASH_KEY_1", "fake-gemini")
    # APIClient also builds a WhisperClient, which insists on at
    # least one Whisper key at construction time.
    monkeypatch.setenv("GROQ_WHISPER_LARGE_V3_KEY_1", "fake-whisper")

    from api.client import APIClient

    client = APIClient()
    try:
        yield client
    finally:
        client.shutdown()


class _StubProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate(self, **kwargs: Any) -> dict:
        self.calls.append(kwargs)
        return {
            "content": "{}",
            "actual_tokens": 1,
            "finish_reason": "stop",
            "usage": None,
            "rate_limit_headers": {},
            "raw_response": None,
        }


def test_gateway_default_is_inert(api_client):
    stub = _StubProvider()
    api_client.providers["groq"] = stub

    response = api_client.generate(
        task="t",
        estimated_tokens=10,
        provider="groq",
        messages=[{"role": "user", "content": "hi"}],
    )

    assert response.success
    assert stub.calls[0]["json_mode"] is False


def test_gateway_json_maps_to_provider(api_client):
    stub = _StubProvider()
    api_client.providers["gemini"] = stub

    response = api_client.generate(
        task="t",
        estimated_tokens=10,
        provider="gemini",
        prompt="Return JSON.",
        response_format="json",
    )

    assert response.success
    assert stub.calls[0]["json_mode"] is True


def test_gateway_rejects_unknown_format(api_client):
    with pytest.raises(ValueError, match="response_format"):
        api_client.generate(
            task="t",
            estimated_tokens=10,
            provider="groq",
            messages=[{"role": "user", "content": "hi"}],
            response_format="xml",
        )
