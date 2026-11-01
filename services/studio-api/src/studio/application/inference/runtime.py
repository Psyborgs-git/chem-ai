"""Bounded OpenAI-compatible Chat/Responses transport with pinned destinations.

No redirect, environment proxy, or arbitrary URL tool is supported. Provider
response bodies are untrusted data and credential echoes are redacted before
they can enter a session, a tool invocation, or a returned error.
"""

from __future__ import annotations

import base64
import copy
import http.client
import ipaddress
import json
import socket
import ssl
import threading
import time
from typing import Any, cast
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from studio.application.inference.secrets import SecretStore, get_secret_store
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import InferenceProvider

MAX_RESPONSE_BYTES = 1024 * 1024
RESPONSES_OUTPUT = "_responses_output"


def _response_items(items: Any) -> list[dict[str, Any]]:
    """Keep protocol items and opaque encrypted state; never retain reasoning text."""
    if not isinstance(items, list) or len(items) > 100:
        raise RuntimeError("provider returned invalid Responses output items")
    result: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("provider returned an invalid Responses output item")
        kind = item.get("type")
        if kind == "reasoning":
            encrypted = item.get("encrypted_content")
            if not isinstance(encrypted, str) or not encrypted:
                # Plaintext reasoning is neither exposed nor copied into history.
                # Stateless reasoning continuity requires the requested encrypted item.
                raise RuntimeError(
                    "provider omitted encrypted reasoning state requested for stateless use"
                )
            opaque: dict[str, Any] = {
                "type": "reasoning",
                "encrypted_content": encrypted,
                "summary": [],
            }
            if isinstance(item.get("id"), str):
                opaque["id"] = item["id"]
            result.append(opaque)
        elif kind == "function_call":
            if any(
                not isinstance(item.get(key), str) or not item[key]
                for key in ("call_id", "name", "arguments")
            ):
                raise RuntimeError("provider returned an invalid Responses function call")
            call = {key: item[key] for key in ("type", "call_id", "name", "arguments")}
            if isinstance(item.get("id"), str):
                call["id"] = item["id"]
            result.append(call)
        elif kind == "message":
            if item.get("role") != "assistant" or not isinstance(item.get("content"), list):
                raise RuntimeError("provider returned an invalid Responses message")
            content = []
            for part in item["content"]:
                if not isinstance(part, dict):
                    raise RuntimeError("provider returned invalid Responses message content")
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    content.append({"type": "output_text", "text": part["text"], "annotations": []})
                elif part.get("type") == "refusal" and isinstance(part.get("refusal"), str):
                    content.append({"type": "refusal", "refusal": part["refusal"]})
                else:
                    raise RuntimeError("provider returned unsupported Responses message content")
            message: dict[str, Any] = {"type": "message", "role": "assistant", "content": content}
            if isinstance(item.get("id"), str):
                message["id"] = item["id"]
            result.append(message)
        else:
            raise RuntimeError("provider returned an unsupported Responses output item")
    return result


def _responses_input(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    instructions: list[str] = []
    inputs: list[dict[str, Any]] = []
    for message in messages:
        role, content = message.get("role"), message.get("content")
        if role in {"system", "developer"}:
            if not isinstance(content, str):
                raise RuntimeError("Responses system instructions must be text")
            instructions.append(content)
        elif role == "assistant" and RESPONSES_OUTPUT in message:
            # Replay exact function identities and encrypted state in their
            # original output order, rather than duplicating normalized calls.
            inputs.extend(_response_items(message[RESPONSES_OUTPUT]))
        elif role == "tool":
            if not isinstance(message.get("tool_call_id"), str) or not isinstance(content, str):
                raise RuntimeError("Responses tool output requires a call identity and text")
            inputs.append(
                {
                    "type": "function_call_output",
                    "call_id": message["tool_call_id"],
                    "output": content,
                }
            )
        elif role in {"user", "assistant"}:
            if content is not None and not isinstance(content, str):
                raise RuntimeError("Responses conversation content must be text")
            if content:
                inputs.append({"role": role, "content": content})
            if role == "assistant":
                for call in message.get("tool_calls") or []:
                    function = call.get("function") or {}
                    inputs.append(
                        {
                            "type": "function_call",
                            "call_id": call["id"],
                            "name": function["name"],
                            "arguments": function["arguments"],
                        }
                    )
        else:
            raise RuntimeError("Responses conversation role is unsupported")
    return "\n\n".join(instructions), inputs


def _normalize_response(response: dict[str, Any]) -> dict[str, Any]:
    if response.get("status") not in {None, "completed"}:
        raise RuntimeError(
            "provider Responses request did not complete; review its model and output budget"
        )
    items = _response_items(response.get("output"))
    text: list[str] = []
    calls: list[dict[str, Any]] = []
    for item in items:
        if item["type"] == "message":
            text.extend(part.get("text") or part.get("refusal") or "" for part in item["content"])
        elif item["type"] == "function_call":
            calls.append(
                {
                    "id": item["call_id"],
                    "type": "function",
                    "function": {"name": item["name"], "arguments": item["arguments"]},
                }
            )
    message: dict[str, Any] = {"role": "assistant", "content": "\n".join(text) or None}
    if calls:
        message["tool_calls"] = calls
    raw_usage = response.get("usage") or {}
    usage: dict[str, Any] = {}
    if isinstance(raw_usage, dict):
        for original, normalized in (
            ("input_tokens", "prompt_tokens"),
            ("output_tokens", "completion_tokens"),
            ("total_tokens", "total_tokens"),
        ):
            value = raw_usage.get(original)
            if isinstance(value, int) and value >= 0:
                usage[normalized] = value
        if (
            "total_tokens" not in usage
            and "prompt_tokens" in usage
            and "completion_tokens" in usage
        ):
            usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return {"choices": [{"message": message}], "usage": usage, RESPONSES_OUTPUT: items}


def retain_response_state(message: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    """Attach opaque transport state to private model history, never UI messages."""
    if RESPONSES_OUTPUT not in response:
        return message
    items = copy.deepcopy(_response_items(response[RESPONSES_OUTPUT]))
    known = {item["call_id"] for item in items if item["type"] == "function_call"}
    for call in message.get("tool_calls") or []:
        # A compatible model may emit the legacy JSON tool shape as text.
        # The local interpreter's normalized call still needs a correlated
        # input item before its function_call_output in stateless history.
        if call["id"] not in known:
            function = call["function"]
            items.append(
                {
                    "type": "function_call",
                    "call_id": call["id"],
                    "name": function["name"],
                    "arguments": function["arguments"],
                }
            )
    return {**message, RESPONSES_OUTPUT: items}


def validate_base_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        host = parsed.hostname or ""
        port = parsed.port
        if (
            not host
            or parsed.scheme not in {"http", "https"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(ord(c) < 33 for c in value)
            or "\\" in value
            or port == 0
            or any(p in {".", ".."} for p in unquote(parsed.path).split("/"))
        ):
            raise ValueError
        loopback = host.lower() == "localhost"
        try:
            address = ipaddress.ip_address(host)
            loopback = address.is_loopback
            if not loopback and not address.is_global:
                raise ValueError
        except ValueError:
            if ":" in host or host.replace(".", "").isdigit():
                raise
        if parsed.scheme != "https" and not loopback:
            raise ValueError
        # Explicitly canonicalize only trailing slashes. Rebinding a stored
        # credential to any changed destination/path requires replacement.
        return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))
    except (ValueError, UnicodeError):
        raise DomainError(
            ErrorCode.VALIDATION,
            "baseUrl must use HTTPS or explicit loopback HTTP, "
            "with no credentials, query or fragment",
            field_path="baseUrl",
        ) from None


def is_loopback_url(value: str) -> bool:
    host = urlsplit(value).hostname or ""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _destination(value: str) -> tuple[str, int, str, bool]:
    parsed = urlsplit(validate_base_url(value))
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(str(answer[4][0]) for answer in answers))
        if host.lower() == "localhost":
            addresses.sort(key=lambda item: ipaddress.ip_address(item).version)
        if not addresses:
            raise OSError
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if is_loopback_url(value):
                if not ip.is_loopback:
                    raise OSError
            elif not ip.is_global:
                raise OSError
        return host, port, addresses[0], parsed.scheme == "https"
    except (OSError, ValueError):
        raise RuntimeError(
            "provider destination is unavailable or is not an allowed address"
        ) from None


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, address: str, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


class _PinnedHTTPS(_PinnedHTTP):
    def connect(self) -> None:
        plain = socket.create_connection((self._address, self.port), self.timeout)
        try:
            self.sock = ssl.create_default_context().wrap_socket(plain, server_hostname=self.host)
        except BaseException:
            plain.close()
            raise


class OpenAICompatibleRuntime:
    supports_native_tools = True

    def __init__(
        self,
        config: InferenceProvider,
        secret_store: SecretStore | None = None,
        *,
        model_id: str | None = None,
        supports_tools: bool | None = None,
        api_style: str | None = None,
    ) -> None:
        self.config = config
        self._store = secret_store or get_secret_store()
        self.model_id = model_id or config.model
        self.supports_tools = config.supports_tools if supports_tools is None else supports_tools
        self.api_style = config.api_style if api_style in {None, "inherit"} else api_style
        if self.api_style not in {"chat_completions", "responses"}:
            raise RuntimeError("unsupported inference API style")

    def running(self) -> bool:
        return self.config.enabled

    @property
    def provenance(self) -> dict[str, str]:
        return {
            "provider_id": str(self.config.id),
            "provider_name": self.config.name,
            "model": self.model_id,
            "base_url": self.config.base_url,
            "api_style": self.api_style,
        }

    def _request(
        self, method: str, endpoint: str, body: dict[str, Any] | None, timeout: float
    ) -> dict[str, Any]:
        secret = (
            self._store.get(self.config.workspace_id, self.config.credential_ref)
            if self.config.credential_ref
            else ""
        )
        host, port, address, tls = _destination(self.config.base_url)
        connection = (_PinnedHTTPS if tls else _PinnedHTTP)(host, port, address, max(0.1, timeout))
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        path = (urlsplit(self.config.base_url).path.rstrip("/") + endpoint) or "/"
        started = time.monotonic()

        def interrupt() -> None:
            # A peer that drips headers/body must not reset the overall turn
            # budget indefinitely. Closing the socket also unblocks read().
            if connection.sock is not None:
                try:
                    connection.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()

        timer = threading.Timer(max(0.1, timeout), interrupt)
        timer.daemon = True
        timer.start()
        try:
            connection.request(
                method, path, json.dumps(body).encode() if body is not None else None, headers
            )
            response = connection.getresponse()
            # http.client never follows redirects. Neither body nor headers
            # from any upstream failure is included in the public diagnostic.
            if not 200 <= response.status < 300:
                raise RuntimeError(
                    f"provider returned HTTP {response.status}; verify endpoint, key and model"
                )
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise RuntimeError("provider response exceeded the allowed size")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise RuntimeError("provider returned an invalid JSON response")
            variants = (
                {secret, quote(secret, safe=""), base64.b64encode(secret.encode()).decode()}
                if secret
                else set()
            )

            def clean(value: Any) -> Any:
                if isinstance(value, str):
                    for variant in sorted(variants, key=len, reverse=True):
                        value = value.replace(variant, "[REDACTED]")
                    return value
                if isinstance(value, list):
                    return [clean(item) for item in value]
                if isinstance(value, dict):
                    return {clean(key): clean(item) for key, item in value.items()}
                return value

            sanitized = cast(dict[str, Any], clean(result))
            if time.monotonic() - started >= timeout:
                raise RuntimeError("provider request exceeded its time budget")
            return sanitized
        except (OSError, http.client.HTTPException, ValueError, RecursionError):
            raise RuntimeError(
                "provider request failed; verify the endpoint and connection"
            ) from None
        finally:
            timer.cancel()
            connection.close()

    def models(self, *, timeout: float = 10) -> dict[str, Any]:
        return self._request("GET", "/models", None, timeout)

    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 256,
        temperature: float = 0.0,
        grammar: str | None = None,
        timeout: float = 120.0,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if self.api_style == "responses":
            instructions, inputs = _responses_input(messages)
            response_body: dict[str, Any] = {
                "model": self.model_id,
                "input": inputs,
                "stream": False,
                "store": False,
                "max_output_tokens": max_tokens,
                "include": ["reasoning.encrypted_content"],
            }
            if instructions:
                response_body["instructions"] = instructions
            if tools and self.supports_tools:
                response_body["tools"] = [
                    {
                        "type": "function",
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["input_schema"],
                        "strict": False,
                    }
                    for tool in tools
                ]
            return _normalize_response(
                self._request("POST", "/responses", response_body, min(120, timeout))
            )
        body: dict[str, Any] = {
            "model": self.model_id,
            "messages": [
                {
                    key: value
                    for key, value in message.items()
                    if key in {"role", "content", "tool_call_id", "tool_calls", "name"}
                }
                for message in messages
            ],
            "stream": False,
        }
        if self.config.kind == "openai":
            body.update(max_completion_tokens=max_tokens, store=False)
        else:
            body["max_tokens"] = max_tokens
        if tools and self.supports_tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["input_schema"],
                    },
                }
                for tool in tools
            ]
        return self._request("POST", "/chat/completions", body, min(120, timeout))
