from typing import Any

import pytest
from pydantic import ValidationError

from apris_server.assistant import (
    AssistantCommandRequest,
    AssistantIntentDefinition,
    AssistantIntentInterpreter,
)

CARRY_INTENT = AssistantIntentDefinition(
    id="follow_person",
    description="Follow a person while helping carry an item.",
    examples=["荷物を運ぶのを手伝って", "Help me carry this"],
    keywords=["運ん", "手伝って", "ついて", "carry", "follow"],
    response="Okay. I will follow you.",
)
COME_INTENT = AssistantIntentDefinition(
    id="come_here",
    description="Approach the visible person.",
    examples=["こっちに来て", "Come here"],
    keywords=["来て", "きて", "come here"],
    response="Okay. I am coming.",
)
GUIDE_INTENT = AssistantIntentDefinition(
    id="guide_visitor",
    description="Guide a visitor to a configured destination marker.",
    examples=["入口まで案内して", "Guide me to the entrance"],
    keywords=["案内", "guide", "show me"],
    response="Okay. I will guide you.",
)


class FakeTransport:
    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def create(self, *, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"api_key": api_key, "payload": payload})
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


def response_with_text(text: str) -> dict[str, Any]:
    return {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": text}],
            }
        ]
    }


async def test_rule_interpreter_maps_carry_request_to_bounded_follow_action() -> None:
    interpreter = AssistantIntentInterpreter(None)

    result = await interpreter.interpret(
        "この荷物を机まで運ぶのを手伝って",
        [CARRY_INTENT],
    )

    assert result.action == "follow_person"
    assert result.destination == "desk"
    assert result.follow_distance == "normal"
    assert result.source == "rules"


async def test_rule_interpreter_prefers_the_more_specific_keyword() -> None:
    interpreter = AssistantIntentInterpreter(None)

    result = await interpreter.interpret(
        "机までついてきて",
        [COME_INTENT, CARRY_INTENT],
    )

    assert result.action == "follow_person"


async def test_rule_interpreter_maps_guide_request_and_destination() -> None:
    interpreter = AssistantIntentInterpreter(None)

    result = await interpreter.interpret(
        "入口まで案内して",
        [CARRY_INTENT, GUIDE_INTENT],
    )

    assert result.action == "guide_visitor"
    assert result.destination == "entrance"
    assert result.source == "rules"


async def test_stop_bypasses_configured_llm() -> None:
    transport = FakeTransport(response_with_text("{}"))
    interpreter = AssistantIntentInterpreter("secret", transport=transport)

    result = await interpreter.interpret("Stop right now")

    assert result.action == "stop"
    assert result.source == "rules"
    assert transport.calls == []


async def test_openai_output_is_validated_against_allowlist() -> None:
    transport = FakeTransport(
        response_with_text(
            '{"action":"follow_person","destination":"kitchen",'
            '"follow_distance":"far","response":"I will follow you to the kitchen."}'
        )
    )
    interpreter = AssistantIntentInterpreter("secret", "gpt-6-luna", transport)

    result = await interpreter.interpret(
        "Give me a little more space and help with this",
        [CARRY_INTENT],
    )

    assert result.action == "follow_person"
    assert result.destination == "kitchen"
    assert result.follow_distance == "far"
    assert result.source == "openai"
    payload = transport.calls[0]["payload"]
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True
    assert "velocity" not in payload["text"]["format"]["schema"]["properties"]
    assert payload["text"]["format"]["schema"]["properties"]["action"]["enum"] == [
        "stop",
        "wait_here",
        "report_status",
        "clarify",
        "follow_person",
    ]


async def test_provider_failure_falls_back_to_safe_rules() -> None:
    transport = FakeTransport(error=RuntimeError("offline"))
    interpreter = AssistantIntentInterpreter("secret", transport=transport)

    result = await interpreter.interpret("drive forward at full speed")

    assert result.action == "clarify"
    assert result.source == "rules"


def test_request_rejects_duplicate_and_reserved_intents() -> None:
    intent = CARRY_INTENT.model_dump()
    with pytest.raises(ValidationError, match="intent ids must be unique"):
        AssistantCommandRequest(text="help", intents=[intent, intent])
    with pytest.raises(ValidationError, match="reserved intent id"):
        AssistantCommandRequest(
            text="stop",
            intents=[{**intent, "id": "stop"}],
        )
