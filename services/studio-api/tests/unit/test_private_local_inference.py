from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from studio.domain.agent_workspace.runtime import _calls
from studio.domain.learning.workspace import LearningWorkspaceService
from studio.domain.learning.workspace_runtime import dispatcher
from studio.errors import DomainError, ErrorCode


@pytest.mark.parametrize(
    "answer",
    [
        {"answer": "4", "citations": []},
        {"result": {"formula": "C2H6O"}, "scientificStatus": "not_validated"},
        {"final": "4", "citations": []},
        {"answer": "Example only", "tool": "create_notebook", "arguments": {}, "citations": []},
    ],
)
def test_structured_learned_answers_are_content_instead_of_empty_legacy_envelopes(answer):
    content = json.dumps(answer)
    assert _calls({"role": "assistant", "content": content}) == ([], content)


def test_explicit_legacy_final_envelope_still_unwraps_and_rejects_empty_answer():
    assert _calls({"content": '{"final":"Four."}'}) == ([], "Four.")
    with pytest.raises(RuntimeError, match="empty response"):
        _calls({"content": '{"final":""}'})


def local_service():
    service = object.__new__(LearningWorkspaceService)
    service.settings = SimpleNamespace()
    model = SimpleNamespace(
        id="private-model", backend="mlx", details={"state": "ready"}
    )
    service._owned = lambda *_: model
    return service


@pytest.mark.parametrize("catalog_style", ["application", "openai"])
def test_native_tool_catalog_and_openai_tools_reach_the_same_template_and_allowlist(
    monkeypatch, catalog_style
):
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    }
    function = {
        "name": "search_private_library", "description": "Search notes.", "parameters": schema
    }
    tools = (
        [{"name": function["name"], "description": function["description"], "input_schema": schema}]
        if catalog_style == "application"
        else [{"type": "function", "function": function}]
    )
    original = copy.deepcopy(tools)
    captured = {}

    def preview(*_args, **kwargs):
        captured.update(kwargs)
        return {
            "text": '<tool_call>{"name":"search_private_library",'
            '"arguments":{"query":"ethanol"}}</tool_call>'
        }

    monkeypatch.setattr(dispatcher, "run_preview", preview)
    response = local_service().infer_model(
        "private-model", [{"role": "user", "content": "Find ethanol notes."}], tools
    )
    assert captured["tools"] == [{"type": "function", "function": function}]
    assert tools == original
    calls, _ = _calls(response["choices"][0]["message"])
    assert len(calls) == 1
    assert calls[0]["name"] == "search_private_library"
    assert calls[0]["arguments"] == {"query": "ethanol"}


def test_local_tool_allowlist_still_excludes_model_invented_tools(monkeypatch):
    monkeypatch.setattr(
        dispatcher,
        "run_preview",
        lambda *_args, **_kwargs: {
            "text": '<tool_call>{"name":"delete_everything","arguments":{}}</tool_call>'
        },
    )
    with pytest.raises(DomainError, match="unsupported or malformed tool calls"):
        local_service().infer_model(
            "private-model",
            [{"role": "user", "content": "Read my notes."}],
            [{"name": "read_note", "input_schema": {"type": "object"}}],
        )


@pytest.mark.parametrize("name_key", ["tool", "name"])
def test_structured_answer_metadata_is_not_promoted_to_a_local_tool_call(monkeypatch, name_key):
    content = json.dumps(
        {"answer": "Example only", name_key: "create_notebook", "arguments": {"title": "Draft"}}
    )
    monkeypatch.setattr(
        dispatcher, "run_preview", lambda *_args, **_kwargs: {"text": content}
    )
    response = local_service().infer_model(
        "private-model",
        [{"role": "user", "content": "Explain a notebook command."}],
        [{"name": "create_notebook", "input_schema": {"type": "object"}}],
    )
    message = response["choices"][0]["message"]
    assert "tool_calls" not in message
    assert _calls(message) == ([], content)


@pytest.mark.parametrize(
    "tools",
    [[None], [{"name": "", "input_schema": {}}], [{"name": "read_note", "input_schema": []}]],
)
def test_malformed_local_tool_schema_fails_before_loading_a_model(monkeypatch, tools):
    def forbidden_preview(*_args, **_kwargs):
        raise AssertionError("Malformed tool catalog reached model loading")

    monkeypatch.setattr(dispatcher, "run_preview", forbidden_preview)
    with pytest.raises(DomainError, match="tools"):
        local_service().infer_model(
            "private-model", [{"role": "user", "content": "Hello."}], tools
        )


@pytest.mark.parametrize(
    "content",
    [
        'Example only:\n```xml\n<tool_call>{"name":"read_note",'
        '"arguments":{}}</tool_call>\n```',
        'Here is an example: <tool_call>{"name":"read_note","arguments":{}}</tool_call>',
        '<tool_call>{"name":"read_note","arguments":{}}</tool_call> is example syntax.',
        '<tool_call>{"name":"read_note","arguments":{}}</tool_call>\nExample only:\n'
        '<tool_call>{"name":"read_note","arguments":{}}</tool_call>',
        json.dumps({"answer": 'Example <tool_call>{"name":"read_note",'
                   '"arguments":{}}</tool_call> only.'}),
        json.dumps({"answer": "Example", "tool": "read_note", "arguments": []}),
    ],
)
def test_literal_tool_examples_and_structured_answer_tags_never_execute_or_disappear(
    monkeypatch, content
):
    monkeypatch.setattr(dispatcher, "run_preview", lambda *_args, **_kwargs: {"text": content})
    response = local_service().infer_model(
        "private-model", [{"role": "user", "content": "Explain tool syntax."}],
        [{"name": "read_note", "input_schema": {"type": "object"}}],
    )
    message = response["choices"][0]["message"]
    assert "tool_calls" not in message
    assert message["content"] == content
    assert _calls(message) == ([], content)


@pytest.mark.parametrize(
    "content",
    [
        '{"tool":"read_note","arguments":[]}',
        '{"name":"read_note","arguments":"not an object"}',
        '{"name":"delete_everything","arguments":{}}',
        '<tool_call>{"name":"read_note","arguments":[]}</tool_call>',
        '<tool_call>not JSON</tool_call>',
    ],
)
def test_malformed_or_unsupported_standalone_protocol_is_a_typed_failure(monkeypatch, content):
    monkeypatch.setattr(dispatcher, "run_preview", lambda *_args, **_kwargs: {"text": content})
    with pytest.raises(DomainError) as error:
        local_service().infer_model(
            "private-model", [{"role": "user", "content": "Read a note."}],
            [{"name": "read_note", "input_schema": {"type": "object"}}],
        )
    assert error.value.code == ErrorCode.MODEL_INCOMPATIBLE


def test_standalone_native_blocks_keep_multiple_calls_and_json_encoded_arguments(monkeypatch):
    content = (
        '<tool_call>{"name":"read_note","arguments":"{\\"id\\":\\"page-one\\"}"}'
        '</tool_call>\n\n'
        '<tool_call>{"name":"read_note","arguments":{"id":"page-two"}}</tool_call>'
    )
    monkeypatch.setattr(dispatcher, "run_preview", lambda *_args, **_kwargs: {"text": content})
    response = local_service().infer_model(
        "private-model", [{"role": "user", "content": "Read two notes."}],
        [{"name": "read_note", "input_schema": {"type": "object"}}],
    )
    calls, answer = _calls(response["choices"][0]["message"])
    assert answer == ""
    assert [call["arguments"] for call in calls] == [{"id": "page-one"}, {"id": "page-two"}]


def test_malformed_exact_legacy_envelope_is_not_a_successful_final_answer():
    with pytest.raises(DomainError) as error:
        _calls({"content": '{"tool":"read_note","arguments":[]}'})
    assert error.value.code == ErrorCode.MODEL_INCOMPATIBLE


def test_native_http_calls_with_separate_explanatory_content_remain_supported():
    message = {
        "content": "I will read that note.",
        "tool_calls": [{
            "id": "native-call", "type": "function",
            "function": {"name": "read_note", "arguments": '{"id":"page-one"}'},
        }],
    }
    calls, answer = _calls(message)
    assert calls == [{"id": "native-call", "name": "read_note", "arguments": {"id": "page-one"}}]
    assert answer == "I will read that note."
