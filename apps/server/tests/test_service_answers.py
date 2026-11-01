from unittest.mock import AsyncMock

import pytest

from apris_server.assistant import (
    AnswerRequest,
    AssistantDecision,
    AssistantIntentInterpreter,
)


def question():
    return AnswerRequest(question="Would you like help?", text="That would be great",
                         choices=[{"value": "Yes", "label": "Yes"},
                                  {"value": "No", "label": "No"}])


@pytest.mark.parametrize("action,expected", [("answer_0", "Yes"), ("answer_1", "No"),
                                               ("clarify", None), ("stop", None),
                                               ("follow_person", None)])
async def test_answer_only_returns_supplied_choices(action, expected):
    interpreter = AssistantIntentInterpreter("test", mode="gemini")
    interpreter.provider.interpret = AsyncMock(return_value=AssistantDecision(
        action=action, destination=None, follow_distance="normal", response="Test"))
    result = await interpreter.interpret_answer(question())
    assert result.value == expected
    assert result.source == "gemini"
    prompt, intents = interpreter.provider.interpret.call_args.args
    assert "not consent" in prompt
    assert [i.id for i in intents] == ["answer_0", "answer_1"]


async def test_rules_and_cloud_failure_do_not_authorize_answers():
    assert (await AssistantIntentInterpreter(None).interpret_answer(question())).value is None
    interpreter = AssistantIntentInterpreter("test", mode="gemini")
    interpreter.provider.interpret = AsyncMock(side_effect=RuntimeError("failed"))
    result = await interpreter.interpret_answer(question())
    assert result.value is None
    assert result.source == "rules"
