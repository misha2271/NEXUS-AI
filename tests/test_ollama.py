"""Protocol tests use local in-memory HTTP fixtures, never simulated app telemetry."""

from __future__ import annotations

import json
from threading import Event

import httpx
import pytest

from nexus_ai.ollama import OllamaClient, OllamaError, OllamaModel


def client_for(handler, **kwargs):
    return OllamaClient("http://localhost:11434", transport=httpx.MockTransport(handler), **kwargs)


def test_discovery_preserves_base_path_and_parses_sizes():
    def handle(request):
        assert request.url == "http://localhost:11434/ollama/api/tags"
        assert request.method == "GET"
        return httpx.Response(
            200, json={"models": [{"name": "llama3.2:latest", "size": 1234}, {"name": "tiny"}]}
        )

    with OllamaClient(
        "http://localhost:11434/ollama/", transport=httpx.MockTransport(handle)
    ) as client:
        assert client.list_models() == [OllamaModel("llama3.2:latest", 1234), OllamaModel("tiny")]


def test_empty_discovery_is_valid():
    with client_for(lambda _: httpx.Response(200, json={"models": []})) as client:
        assert client.list_models() == []


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"models": {}},
        {"models": [None]},
        {"models": [{}]},
        {"models": [{"name": " "}]},
        {"models": [{"name": "x", "size": -1}]},
        {"models": [{"name": "x", "size": True}]},
    ],
)
def test_malformed_discovery_is_actionable(payload):
    with client_for(lambda _: httpx.Response(200, json=payload)) as client:
        with pytest.raises(OllamaError):
            client.list_models()


def test_malformed_json():
    with client_for(lambda _: httpx.Response(200, text="<html>not ollama</html>")) as client:
        with pytest.raises(OllamaError, match="malformed JSON"):
            client.list_models()


def test_stream_sends_actual_policy_and_history_and_honors_done():
    history = [{"role": "user", "content": "Hello"}]

    def handle(request):
        assert request.url.path == "/api/chat"
        assert request.method == "POST"
        assert json.loads(request.content) == {
            "model": "tiny",
            "messages": history,
            "stream": True,
            "options": {"num_thread": 2, "num_gpu": 0},
            "keep_alive": 0,
        }
        return httpx.Response(
            200,
            text='\n{"message":{"content":"Hello "},"done":false}\n'
            '{"message":{"content":"there"},"done":false}\n'
            '{"message":{"content":"!"},"done":true}\n'
            '{"error":"must never read beyond done"}\n',
        )

    with client_for(handle) as client:
        assert list(
            client.stream_chat(
                "tiny", history, options={"num_thread": 2, "num_gpu": 0}, keep_alive=0
            )
        ) == ["Hello ", "there", "!"]


def test_stream_accepts_done_only_empty_reply():
    with client_for(lambda _: httpx.Response(200, text='{"done":true}\n')) as client:
        assert list(client.stream_chat("tiny", [])) == []


def test_thinking_only_chunks_are_ignored_until_answer():
    text = (
        '{"message":{"role":"assistant","thinking":"reasoning"},"done":false}\n'
        '{"message":{"content":"","thinking":"more reasoning"},"done":false}\n'
        '{"message":{"content":"answer"},"done":false}\n'
        '{"done":true}\n'
    )
    with client_for(lambda _: httpx.Response(200, text=text)) as client:
        assert list(client.stream_chat("thinking-model", [])) == ["answer"]


def test_discovery_server_error_preserves_detail():
    with client_for(lambda _: httpx.Response(200, json={"error": "storage unavailable"})) as client:
        with pytest.raises(OllamaError, match="storage unavailable"):
            client.list_models()


def test_redirect_is_reported_as_http_failure():
    with client_for(lambda _: httpx.Response(302, headers={"Location": "/login"})) as client:
        with pytest.raises(OllamaError, match="HTTP 302"):
            client.list_models()
        with pytest.raises(OllamaError, match="HTTP 302"):
            list(client.stream_chat("tiny", []))


@pytest.mark.parametrize(
    "text,match",
    [
        ("{not json}\n", "malformed JSON"),
        ("[]\n", "JSON object"),
        ('{"done":"true"}\n', "done"),
        ('{"message":{"content":123}}\n', "chat message"),
        ('{"done":false}\n', "without a message"),
        ('{"message":{"content":"partial"}}\n', "disconnected"),
        ("", "disconnected"),
        ('{"error":"model not found"}\n', "ollama pull tiny"),
    ],
)
def test_stream_protocol_failures(text, match):
    with client_for(lambda _: httpx.Response(200, text=text)) as client:
        with pytest.raises(OllamaError, match=match):
            list(client.stream_chat("tiny", []))


def test_cancelled_before_request_performs_no_network_io():
    event = Event()
    event.set()

    def unexpected(_):
        pytest.fail("A cancelled call must not contact the server")

    with client_for(unexpected) as client:
        assert list(client.stream_chat("tiny", [], cancel_event=event)) == []


def test_cancel_during_stream_closes_response():
    event = Event()

    class Stream(httpx.SyncByteStream):
        closed = False

        def __iter__(self):
            yield b'{"message":{"content":"first"},"done":false}\n'
            event.set()
            yield b'{"message":{"content":"second"},"done":false}\n'

        def close(self):
            self.closed = True

    stream = Stream()
    with client_for(lambda _: httpx.Response(200, stream=stream)) as client:
        assert list(client.stream_chat("tiny", [], cancel_event=event)) == ["first"]
    assert stream.closed


@pytest.mark.parametrize(
    "error,match",
    [
        (httpx.ConnectError("connection refused"), "ollama serve"),
        (httpx.ReadTimeout("slow model load"), "timed out"),
        (httpx.RemoteProtocolError("stream broken"), "Cannot reach"),
    ],
)
def test_network_failures_are_actionable_for_both_endpoints(error, match):
    def handle(_):
        raise error

    with client_for(handle) as client:
        with pytest.raises(OllamaError, match=match):
            client.list_models()
        with pytest.raises(OllamaError, match=match):
            list(client.stream_chat("tiny", []))


def test_missing_model_recommends_manual_pull():
    with client_for(lambda _: httpx.Response(404, json={"error": "model not found"})) as client:
        with pytest.raises(OllamaError, match="ollama pull tiny"):
            list(client.stream_chat("tiny", []))


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_server_http_errors_preserve_status(status):
    with client_for(lambda _: httpx.Response(status, json={"error": "server detail"})) as client:
        with pytest.raises(OllamaError, match=f"HTTP {status}.*server detail"):
            client.list_models()
        with pytest.raises(OllamaError, match=f"HTTP {status}.*server detail"):
            list(client.stream_chat("tiny", []))


def test_invalid_model_rejected_without_network():
    with client_for(lambda _: pytest.fail("unexpected request")) as client:
        with pytest.raises(OllamaError, match="Select an installed model"):
            list(client.stream_chat("", []))


@pytest.mark.parametrize(
    "url",
    [
        "",
        "file:///tmp/ollama",
        "http://",
        "http://user:secret@localhost",
        "http://localhost?token=secret",
        "http://localhost/#chat",
    ],
)
def test_invalid_or_credential_bearing_base_url_rejected(url):
    with pytest.raises(ValueError):
        OllamaClient(url)


def test_explicit_unload_uses_ollama_supported_api_without_generating_text():
    seen = []

    def handle(request):
        seen.append(request)
        assert request.url.path == "/api/generate"
        assert request.method == "POST"
        assert json.loads(request.content) == {
            "model": "qwen3:8b",
            "prompt": "",
            "stream": False,
            "keep_alive": 0,
        }
        return httpx.Response(200, json={"done": True, "done_reason": "unload"})

    with client_for(handle) as client:
        assert client.unload_model(" qwen3:8b ") is None
    assert len(seen) == 1


def test_unload_rejects_missing_model_without_network():
    with client_for(lambda _: pytest.fail("unexpected request")) as client:
        with pytest.raises(OllamaError, match="Select an installed model"):
            client.unload_model(" ")


def test_unload_never_reports_success_without_done_marker():
    with client_for(lambda _: httpx.Response(200, json={"done": False})) as client:
        with pytest.raises(OllamaError, match="done"):
            client.unload_model("qwen3:8b")


def test_unload_propagates_network_errors_and_http_errors():
    with client_for(lambda _: httpx.Response(503, json={"error": "service down"})) as client:
        with pytest.raises(OllamaError, match="503"):
            client.unload_model("qwen3:8b")

    def offline(_):
        raise httpx.ConnectError("offline")

    with client_for(offline) as client:
        with pytest.raises(OllamaError, match="Cannot reach Ollama"):
            client.unload_model("qwen3:8b")
