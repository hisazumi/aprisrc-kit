import json
from urllib import error

import pytest
from test_assistant import CARRY_INTENT, FakeTransport

from apris_server.assistant import AssistantIntentInterpreter, UrllibGeminiTransport
from apris_server.config import AppConfig


def response(action="follow_person"):
    return {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "action": action,
                                    "destination": None,
                                    "follow_distance": "normal",
                                    "response": "Okay.",
                                }
                            )
                        }
                    ]
                },
            }
        ]
    }


async def test_gemini_structured_decision_and_contract():
    transport = FakeTransport(response())
    interpreter = AssistantIntentInterpreter("secret", "gemini-test", transport, mode="gemini")
    result = await interpreter.interpret("Please assist with my bag", [CARRY_INTENT])
    assert result.source == "gemini"
    assert result.model == "gemini-test"
    assert result.action == "follow_person"
    payload = transport.calls[0]["payload"]
    schema = payload["generationConfig"]["responseFormat"]["text"]["schema"]
    assert "follow_person" in schema["properties"]["action"]["enum"]
    assert "velocity" not in schema["properties"]
    assert payload["contents"][0]["parts"][0]["text"] == "Please assist with my bag"


@pytest.mark.parametrize("mode", ["rules", "openai", "gemini"])
async def test_stop_never_calls_any_provider(mode):
    transport = FakeTransport(response())
    interpreter = AssistantIntentInterpreter("secret", transport=transport, mode=mode)
    result = await interpreter.interpret("停止して")
    assert result.source == "rules" and result.action == "stop"
    assert transport.calls == []


async def test_explicit_rules_ignores_configured_key():
    transport = FakeTransport(response())
    interpreter = AssistantIntentInterpreter("secret", transport=transport, mode="rules")
    result = await interpreter.interpret("follow", [CARRY_INTENT])
    assert result.source == "rules"
    assert not interpreter.configured and transport.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"promptFeedback": {"blockReason": "SAFETY"}},
        {"candidates": [{"finishReason": "MAX_TOKENS"}]},
        {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "invalid"}]}}]},
        response("motor_forward"),
        {"candidates": None},
        {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"functionCall": {}}]}}]},
    ],
)
async def test_invalid_gemini_response_uses_rules(body):
    interpreter = AssistantIntentInterpreter("secret", transport=FakeTransport(body), mode="gemini")
    result = await interpreter.interpret("unsupported request")
    assert result.source == "rules" and result.action == "clarify"


async def test_gemini_network_failure_falls_back():
    interpreter = AssistantIntentInterpreter(
        "secret", transport=FakeTransport(error=RuntimeError("offline")), mode="gemini"
    )
    assert (await interpreter.interpret("follow", [CARRY_INTENT])).source == "rules"


def test_provider_environment_and_key_isolation(tmp_path):
    base = {"OPENAI_API_KEY": "openai-secret", "GEMINI_API_KEY": "gemini-secret"}
    for mode, key in [("rules", None), ("openai", "openai-secret"), ("gemini", "gemini-secret")]:
        c = AppConfig.from_environment(tmp_path, {**base, "APRIS_ASSISTANT_PROVIDER": mode})
        assert c.assistant_provider == mode
        assert c.assistant_api_key_value() == key
        assert "openai-secret" not in repr(c) and "gemini-secret" not in repr(c)
    c = AppConfig.from_environment(
        tmp_path,
        {**base, "APRIS_ASSISTANT_PROVIDER": "gemini", "APRIS_ASSISTANT_MODEL": "gemini-custom"},
    )
    assert c.assistant_model == "gemini-custom"
    assert AppConfig.from_environment(tmp_path, base).assistant_api_key_value() == "openai-secret"


@pytest.mark.parametrize("mode", ["openai", "gemini", "invalid"])
def test_missing_or_invalid_provider_fails_configuration(tmp_path, mode):
    with pytest.raises(ValueError):
        AppConfig.from_environment(tmp_path, {"APRIS_ASSISTANT_PROVIDER": mode})


def test_http_request_keeps_key_out_of_url(monkeypatch):
    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b"{}"

    def open_request(req, timeout):
        assert (
            req.full_url
            == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
        )
        assert "secret" not in req.full_url
        assert req.get_header("X-goog-api-key") == "secret"
        assert timeout == 12
        assert json.loads(req.data) == {"contents": []}
        return Reply()

    monkeypatch.setattr("apris_server.assistant.request.urlopen", open_request)
    assert UrllibGeminiTransport("gemini-test")._create_sync("secret", {"contents": []}) == {}


@pytest.mark.parametrize(
    "failure",
    [TimeoutError(), error.URLError("secret"), error.HTTPError("url", 429, "secret", {}, None)],
)
def test_transport_errors_are_sanitized(monkeypatch, failure):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr("apris_server.assistant.request.urlopen", fail)
    with pytest.raises(RuntimeError) as exc:
        UrllibGeminiTransport("gemini-test")._create_sync("secret", {})
    assert "secret" not in str(exc.value)


def test_model_cannot_change_endpoint():
    with pytest.raises(ValueError):
        UrllibGeminiTransport("../../other?key=secret")
