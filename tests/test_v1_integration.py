"""Desktop service integration across launches, cancellation and async shutdown."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QTimer
from shiboken6 import isValid

from nexus_ai.conversations import ConversationStore
from nexus_ai.gaming import GameDetection, GameProfile
from nexus_ai.ollama import OllamaModel
from nexus_ai.settings import SettingsStore
from nexus_ai.ui.window import MainWindow


class Server:
    def __init__(self):
        self.requests = []
        self.block = None
        self.entered = threading.Event()

    def client(self, url):
        fixture = self

        class Client:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def list_models(self):
                return [OllamaModel("local:test")]

            def stream_chat(self, model, messages, **kwargs):
                fixture.requests.append(messages)
                fixture.entered.set()
                if fixture.block is not None:
                    fixture.block.wait(5)
                yield "Сохранённый ответ <raw>"

        return Client()


@pytest.fixture
def desktop(qtbot, tmp_path):
    windows = []
    releases = []
    server = Server()

    def create():
        window = MainWindow(
            SettingsStore(tmp_path / "settings.json"),
            client_factory=server.client,
            start_background=False,
        )
        windows.append(window)
        qtbot.addWidget(window)
        window.show()
        window.refresh_models()
        qtbot.waitUntil(lambda: not window._jobs and not window._pool.activeThreadCount())
        return window

    yield create, server, tmp_path, releases
    for event in releases:
        event.set()
    for window in windows:
        if isValid(window):
            window.close()
            qtbot.waitUntil(
                lambda window=window: not isValid(window) or not window.isVisible(), timeout=7000
            )


def idle(qtbot, window):
    qtbot.waitUntil(
        lambda: not window._jobs and not window._pool.activeThreadCount() and not window._v1_busy(),
        timeout=7000,
    )


def test_completed_chat_survives_launch_and_resumes_exact_context(desktop, qtbot):
    create, server, path, _ = desktop
    first = create()
    first.prompt.setPlainText("Первый вопрос <raw>")
    first.send_message()
    idle(qtbot, first)
    records = ConversationStore(path / "conversations.sqlite3").list_conversations()
    assert len(records) == 1
    first.close()
    second = create()
    assert not second._messages  # No conversation silently resumed.
    second.conversations.refresh()
    idle(qtbot, second)
    second.conversations.load_selected()
    idle(qtbot, second)
    assert second._messages == [
        {"role": "user", "content": "Первый вопрос <raw>"},
        {"role": "assistant", "content": "Сохранённый ответ <raw>"},
    ]
    assert "Первый вопрос <raw>" in second.transcript.toPlainText()
    second.prompt.setPlainText("Продолжение")
    second.send_message()
    idle(qtbot, second)
    assert server.requests[-1][0]["content"] == "Первый вопрос <raw>"
    store = ConversationStore(path / "conversations.sqlite3")
    assert len(store.list_conversations()) == 1
    assert len(store.load(records[0].id).messages) == 4


def test_cancelled_reply_is_not_persisted_or_marked_as_owned(desktop, qtbot):
    create, server, path, releases = desktop
    server.block = threading.Event()
    releases.append(server.block)
    window = create()
    window.prompt.setPlainText("Отменить")
    window.send_message()
    qtbot.waitUntil(server.entered.is_set)
    window.stop_generation()
    server.block.set()
    idle(qtbot, window)
    assert window._messages == []
    assert window.game_center.controller.owned_model is None
    assert not (path / "conversations.sqlite3").exists()


def test_russian_text_router_and_remote_profile_preserve_game_override(desktop):
    create, _, _, _ = desktop
    window = create()
    assert window.settings.language == "ru"
    assert not window.voice.status().available
    assert not window.remote_panel.running
    window.command_input.setText("игровой режим")
    window._run_text_command()
    assert window.store.load().profile == "Gaming"
    window.command_input.setText("запусти cmd.exe")
    window._run_text_command()
    assert window.store.load().profile == "Gaming"
    window.game_center._apply(
        window.game_center.controller.observe(
            GameDetection(GameProfile("Игра", ("game.exe",), unload_model=False), (), True, "")
        )
    )
    result = window._approved_command("set_profile", {"profile": "Eco"})
    assert result["profile"] == "Gaming"
    assert window.store.load().profile == "Eco"
    window.game_center._apply(
        window.game_center.controller.observe(GameDetection(None, (), True, ""))
    )
    assert window._effective_profile == "Eco"


def test_close_during_device_scan_keeps_event_loop_responsive(desktop, qtbot):
    create, _, _, releases = desktop
    window = create()
    entered, release = threading.Event(), threading.Event()
    releases.append(release)
    threads = []

    def collect():
        threads.append(threading.get_ident())
        entered.set()
        release.wait(5)
        return SimpleNamespace(message="", disks=())

    window.storage_panel._collector_factory = lambda: SimpleNamespace(collect=collect)
    window.storage_panel.scan()
    qtbot.waitUntil(entered.is_set)
    window.close()
    assert window.isVisible()
    heartbeat = []
    QTimer.singleShot(0, lambda: heartbeat.append(True))
    qtbot.waitUntil(lambda: bool(heartbeat))
    release.set()
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=6000)
    assert len(threads) == 1 and threads[0] != threading.get_ident()
