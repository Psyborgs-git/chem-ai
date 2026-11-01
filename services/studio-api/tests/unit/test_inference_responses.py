"""Real loopback HTTP Responses protocol, opaque reasoning and mixed API models."""

from __future__ import annotations

import json
import threading
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from studio.application.inference.runtime import (
    RESPONSES_OUTPUT,
    OpenAICompatibleRuntime,
    retain_response_state,
)
from studio.persistence.models import InferenceProvider


@contextmanager
def endpoint(responses):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            requests.append({"path": self.path, "body": body})
            result = responses.pop(0)
            encoded = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = InferenceProvider(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        version=1,
        name="Local Responses fixture",
        kind="openai",
        base_url=f"http://127.0.0.1:{server.server_port}/v1",
        model="reasoning-model",
        api_style="responses",
        enabled=True,
        supports_tools=True,
        credential_ref=None,
    )
    try:
        yield config, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def response(call_id="call-one", encrypted="opaque-one"):
    return {
        "id": "response-unused",
        "status": "completed",
        "output": [
            {
                "id": "rs-" + call_id,
                "type": "reasoning",
                "encrypted_content": encrypted,
                "summary": [{"type": "summary_text", "text": "REASONING-SUMMARY-MUST-NOT-PERSIST"}],
                "content": [{"type": "reasoning_text", "text": "RAW-REASONING-MUST-NOT-PERSIST"}],
            },
            {
                "id": "fc-" + call_id,
                "type": "function_call",
                "call_id": call_id,
                "name": "inspect",
                "arguments": '{"query":"ethanol"}',
            },
        ],
        "usage": {"input_tokens": 21, "output_tokens": 9, "total_tokens": 30},
    }


def final():
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg-final",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Completed from actual tool results."}],
            }
        ],
        "usage": {"input_tokens": 31, "output_tokens": 11},
    }


TOOLS = [
    {
        "name": "inspect",
        "description": "Read current facts",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": [],
            "additionalProperties": False,
        },
    }
]


def test_responses_http_roundtrip_preserves_encrypted_reasoning_and_function_identities():
    with endpoint([response(), response("call-two", "opaque-two"), final()]) as (config, requests):
        runtime = OpenAICompatibleRuntime(config)
        messages = [
            {"role": "system", "content": "Use real tool results."},
            {"role": "user", "content": "Inspect ethanol"},
        ]
        first = runtime.generate(messages, tools=TOOLS, max_tokens=2048)
        assert first["usage"] == {"prompt_tokens": 21, "completion_tokens": 9, "total_tokens": 30}
        assert first["choices"][0]["message"]["tool_calls"][0]["id"] == "call-one"
        assert "MUST-NOT-PERSIST" not in json.dumps(first)
        assert first[RESPONSES_OUTPUT][0]["summary"] == []
        messages.extend(
            [
                retain_response_state(first["choices"][0]["message"], first),
                {"role": "tool", "tool_call_id": "call-one", "content": '{"actual":1}'},
            ]
        )
        second = runtime.generate(messages, tools=TOOLS)
        messages.extend(
            [
                retain_response_state(second["choices"][0]["message"], second),
                {"role": "tool", "tool_call_id": "call-two", "content": '{"actual":2}'},
            ]
        )
        result = runtime.generate(messages, tools=TOOLS)
        assert result["choices"][0]["message"]["content"] == "Completed from actual tool results."
        assert result["usage"]["total_tokens"] == 42
        for request in requests:
            assert request["path"] == "/v1/responses"
            assert request["body"]["store"] is False
            assert request["body"]["include"] == ["reasoning.encrypted_content"]
            assert request["body"]["instructions"] == "Use real tool results."
            assert request["body"]["tools"][0]["strict"] is False
            assert "function" not in request["body"]["tools"][0]
            assert "previous_response_id" not in request["body"]
            assert "MUST-NOT-PERSIST" not in json.dumps(request)
        assert requests[0]["body"]["max_output_tokens"] == 2048
        inputs = requests[-1]["body"]["input"]
        assert [
            item["encrypted_content"] for item in inputs if item.get("type") == "reasoning"
        ] == ["opaque-one", "opaque-two"]
        assert [
            item["call_id"] for item in inputs if item.get("type") == "function_call_output"
        ] == ["call-one", "call-two"]
        assert (
            json.loads(
                next(item for item in inputs if item.get("type") == "function_call_output")[
                    "output"
                ]
            )["actual"]
            == 1
        )


def test_model_override_can_mix_chat_and_responses_under_one_provider():
    chat = {"choices": [{"message": {"role": "assistant", "content": "Chat reply"}}]}
    with endpoint([chat, final()]) as (config, requests):
        runtime = OpenAICompatibleRuntime(
            config, model_id="chat-model", api_style="chat_completions"
        )
        runtime.generate([{"role": "user", "content": "Hello", RESPONSES_OUTPUT: []}], tools=TOOLS)
        assert requests[0]["path"] == "/v1/chat/completions"
        assert requests[0]["body"]["model"] == "chat-model"
        assert RESPONSES_OUTPUT not in requests[0]["body"]["messages"][0]
        assert requests[0]["body"]["tools"][0]["function"]["name"] == "inspect"
        inherited = OpenAICompatibleRuntime(config, model_id="response-model", api_style="inherit")
        inherited.generate([{"role": "user", "content": "Hello"}])
        assert requests[1]["path"] == "/v1/responses"
        assert inherited.provenance["api_style"] == "responses"


def test_plain_reasoning_is_refused_when_encrypted_state_is_missing():
    output = response()
    del output["output"][0]["encrypted_content"]
    with endpoint([output]) as (config, _requests):
        with pytest.raises(RuntimeError, match="encrypted reasoning"):
            OpenAICompatibleRuntime(config).generate(
                [{"role": "user", "content": "Inspect"}], tools=TOOLS
            )


def test_incomplete_reasoning_does_not_become_a_fabricated_final_message():
    with endpoint([{**response(), "status": "incomplete"}]) as (config, _requests):
        with pytest.raises(RuntimeError, match="output budget"):
            OpenAICompatibleRuntime(config).generate(
                [{"role": "user", "content": "Inspect"}], tools=TOOLS
            )
