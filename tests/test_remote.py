"""Exercise a real loopback HTTP listener, authorization and Qt queue boundaries."""

from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from http.client import HTTPConnection

import pytest

from nexus_ai.remote import (
    RemoteCommandQueue,
    RemoteConfig,
    RemoteError,
    RemoteServer,
    _csp,
    _page,
    generate_token,
    validate_command,
    validate_config,
    validate_token,
)


@pytest.fixture
def listener():
    token = generate_token()
    calls = []

    def dispatch(command, params):
        calls.append((command, params))
        return {"ok": True, "profile": "Smart"}

    server = RemoteServer(RemoteConfig(enabled=True), token, dispatch)
    server.start()
    yield server, token, calls
    server.stop()


def request(listener, method="GET", path="/api/status", *, headers=None, body=None, auth=True):
    server, token, _ = listener
    connection = HTTPConnection(*server.address, timeout=3)
    headers = dict(headers or {})
    if auth:
        headers.setdefault("Authorization", f"Bearer {token}")
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_token_is_generated_and_validated_without_persistence():
    one, two = generate_token(), generate_token()
    assert one != two
    validate_token(one)
    for value in ("", "short", "https://token", "☃" * 50, "a" * 129):
        with pytest.raises(RemoteError):
            validate_token(value)


@pytest.mark.parametrize(
    "config",
    [
        RemoteConfig(host="0.0.0.0"),
        RemoteConfig(host="::"),
        RemoteConfig(host="224.0.0.1"),
        RemoteConfig(host="example.com"),
        RemoteConfig(host="192.168.1.2"),
        RemoteConfig(port=-1),
        RemoteConfig(port=True),
        RemoteConfig(max_connections=33),
        RemoteConfig(requests_per_minute=0),
        RemoteConfig(request_timeout=True),
        RemoteConfig(request_timeout="30"),
        RemoteConfig(allowed_hosts=("evil.test/path",)),
        RemoteConfig(certfile="/missing/certificate.pem"),
    ],
)
def test_unsafe_listener_configuration_is_rejected(config):
    with pytest.raises(RemoteError):
        validate_config(config)


def test_server_requires_explicit_enable():
    server = RemoteServer(RemoteConfig(), generate_token(), lambda *_: {})
    with pytest.raises(RemoteError, match="disabled"):
        server.start()
    assert server.address is None


def test_listener_socket_is_closed_if_thread_cannot_start(monkeypatch):
    import socket

    from nexus_ai.remote import _BoundedServer

    bound = []
    original_bind = _BoundedServer.server_bind

    def bind(instance):
        original_bind(instance)
        bound.append(instance.server_port)

    def fail(_self):
        raise RuntimeError("thread creation failed")

    monkeypatch.setattr(threading.Thread, "start", fail)
    monkeypatch.setattr(_BoundedServer, "server_bind", bind)
    server = RemoteServer(RemoteConfig(enabled=True), generate_token(), lambda *_: {})
    with pytest.raises(RuntimeError, match="thread creation failed"):
        server.start()
    assert server.address is None and server.origin is None
    assert server._server is None
    # The fixed bind address is still available after failed startup.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", bound[0]))


def test_loopback_requires_authentication_but_page_is_public(listener):
    status, headers, body = request(listener, auth=False)
    assert status == 401 and b"unauthorized" in body
    assert listener[2] == []
    status, _, body = request(listener, path="/", auth=False)
    assert status == 200 and b'<html lang="ru">' in body
    assert listener[1].encode() not in body
    status, headers, body = request(listener)
    assert status == 200 and json.loads(body)["profile"] == "Smart"
    assert listener[2] == [("status", {})]
    assert headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "attacker.test"},
        {"Origin": "https://attacker.test"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Authorization": "Bearer invalid"},
    ],
)
def test_host_origin_and_token_checks_precede_dispatch(listener, headers):
    status, _, _ = request(listener, headers=headers)
    assert status in (401, 403)
    assert listener[2] == []


def test_approved_write_requires_fresh_nonce(listener):
    body = json.dumps(
        {"command": "set_profile", "params": {"profile": "Gaming"}, "nonce": "a" * 32}
    )
    headers = {"Content-Type": "application/json"}
    status, _, _ = request(listener, "POST", "/api/command", headers=headers, body=body)
    assert status == 200 and listener[2] == [("set_profile", {"profile": "Gaming"})]
    status, _, _ = request(listener, "POST", "/api/command", headers=headers, body=body)
    assert status == 409 and len(listener[2]) == 1


@pytest.mark.parametrize(
    "body",
    [
        '{"command":"shell","params":{},"nonce":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',
        '{"command":"status","params":{},"nonce":"a","extra":true}',
        '{"command":"status","command":"stop_generation","params":{},"nonce":"a"}',
        '{"command":"set_profile","params":{"profile":"administrator"},"nonce":"a"}',
        '{"command":"status","params":{"value":NaN},"nonce":"a"}',
    ],
)
def test_unapproved_or_ambiguous_json_never_dispatches(listener, body):
    status, _, _ = request(
        listener, "POST", "/api/command", headers={"Content-Type": "application/json"}, body=body
    )
    assert status == 400 and listener[2] == []


def test_bounded_body_unknown_paths_and_methods(listener):
    status, _, _ = request(listener, path="/api/files")
    assert status == 404
    status, _, _ = request(listener, path="/api/command")
    assert status == 405
    status, _, _ = request(
        listener,
        "POST",
        "/api/command",
        headers={"Content-Type": "application/json"},
        body="x" * 4097,
    )
    assert status == 413 and listener[2] == []


def test_queue_executes_on_draining_thread_only():
    queue = RemoteCommandQueue()
    entered = threading.Event()
    calls = []
    owner = threading.get_ident()

    def submit():
        entered.set()
        return queue.submit("set_profile", {"profile": "Eco"})

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(submit)
        assert entered.wait(1)
        # submit() validates and enqueues before waiting; wait for actual enqueue.
        for _ in range(1000):
            if not queue._queue.empty():
                break
            threading.Event().wait(0.001)
        assert queue.drain(lambda command, params: calls.append(threading.get_ident()) or {}) == 1
        assert future.result(timeout=1) == {}
    assert calls == [owner]


def test_timed_out_and_closed_queue_requests_cannot_execute_later():
    queue = RemoteCommandQueue()
    with pytest.raises(RemoteError, match="timed out"):
        queue.submit("stop_generation", {}, timeout=0.001)
    calls = []
    assert queue.drain(lambda *args: calls.append(args) or {}) == 0
    queue.close()
    with pytest.raises(RemoteError, match="stopped"):
        queue.submit("status", {})
    assert calls == []


def test_command_surface_excludes_hardware_files_prompts_and_shell():
    for command in ("shell", "read_file", "chat", "rgb", "fan", "install_update"):
        with pytest.raises(RemoteError):
            validate_command(command, {})
    assert validate_command("stop_generation", {}) == ("stop_generation", {})


def test_page_scripts_match_content_security_hashes():
    import base64
    import re

    page = _page().decode()
    scripts = re.findall(r"<script>(.*?)</script>", page)
    for script in scripts:
        digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
        assert f"'sha256-{digest}'" in _csp()
    assert "localStorage" not in page and "sessionStorage" not in page


def test_rate_limit_is_enforced():
    token = generate_token()
    server = RemoteServer(
        replace(RemoteConfig(enabled=True), requests_per_minute=1), token, lambda *_: {}
    )
    server.start()
    try:
        listener = server, token, []
        assert request(listener)[0] == 200
        assert request(listener)[0] == 429
    finally:
        server.stop()
