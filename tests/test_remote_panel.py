from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from urllib.parse import urlsplit

from nexus_ai.ui.localization import Translator
from nexus_ai.ui.remote_panel import RemotePanel


def test_remote_is_off_by_default_and_commands_run_on_ui_thread(qtbot):
    owner = threading.get_ident()
    calls = []

    def status():
        calls.append(threading.get_ident())
        return {"profile": "Smart"}

    widget = RemotePanel(Translator("en"), status, lambda *_: {"ok": True})
    qtbot.addWidget(widget)
    assert not widget.running and not widget.busy and not widget.origin
    widget.start()
    qtbot.waitUntil(lambda: not widget.busy, timeout=5000)
    assert widget.running and widget.token.text()
    parsed = urlsplit(widget.origin)
    token = widget.token.text()

    def request():
        connection = HTTPConnection(parsed.hostname, parsed.port, timeout=3)
        connection.request("GET", "/api/status", headers={"Authorization": f"Bearer {token}"})
        response = connection.getresponse()
        payload = response.status, json.loads(response.read())
        connection.close()
        return payload

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(request)
        qtbot.waitUntil(future.done, timeout=5000)
        assert future.result() == (200, {"profile": "Smart"})
    assert calls == [owner]
    widget.shutdown()
    qtbot.waitUntil(lambda: not widget.busy, timeout=5000)
    assert not widget.running and widget.origin is None and not widget.token.text()


def test_shutdown_during_listener_start_still_closes_listener(qtbot):
    widget = RemotePanel(Translator("en"), lambda: {}, lambda *_: {})
    qtbot.addWidget(widget)
    widget.start()
    widget.shutdown()
    qtbot.waitUntil(lambda: not widget.busy, timeout=5000)
    assert not widget.running and not widget._resources


def test_nonloopback_without_tls_fails_without_exposing_token(qtbot):
    widget = RemotePanel(Translator("en"), lambda: {}, lambda *_: {})
    qtbot.addWidget(widget)
    widget.host.setText("192.168.1.2")
    widget.start()
    qtbot.waitUntil(lambda: not widget.busy, timeout=5000)
    assert not widget.running
    assert "TLS" in widget.status.text()
    assert not widget.token.text()
    widget.shutdown()
    qtbot.waitUntil(lambda: not widget.busy, timeout=5000)
