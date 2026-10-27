"""Exercise Game Guard through MainWindow, with no real game or Ollama server."""

from __future__ import annotations

import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest
from shiboken6 import isValid

from nexus_ai.gaming import GameConfiguration, GameProfile, GameProfileStore, ProcessDetector
from nexus_ai.ollama import OllamaModel
from nexus_ai.settings import Settings, SettingsStore
from nexus_ai.ui.window import MainWindow


class Api:
    def __init__(self):
        self.names = []
        self.unloaded = []
        self.threads = []

    def processes(self, **_):
        self.threads.append(threading.get_ident())
        return [SimpleNamespace(info={"name": name}) for name in self.names]

    def client(self, url):
        fixture = self

        class Client:
            def __enter__(self):
                fixture.threads.append(threading.get_ident())
                return self

            def __exit__(self, *_):
                pass

            def list_models(self):
                return [OllamaModel("owned:latest"), OllamaModel("unrelated:latest")]

            def stream_chat(self, *args, **kwargs):
                yield "Ответ"

            def unload_model(self, model):
                fixture.unloaded.append(model)

        return Client()


@pytest.fixture
def integrated(qtbot, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(replace(Settings(), profile="Maximum AI"))
    GameProfileStore(tmp_path / "games.json").save(
        GameConfiguration(True, (GameProfile("Игра", ("game.exe",), "Gaming", True),))
    )
    api = Api()
    window = MainWindow(store, client_factory=api.client, start_background=False)
    window.game_center.detector = ProcessDetector(api.processes)
    qtbot.addWidget(window)
    window.show()
    window.game_center.start()
    qtbot.waitUntil(lambda: not window.game_center.busy)
    yield window, api
    window.close()
    qtbot.waitUntil(
        lambda: not isValid(window) or (not window.isVisible() and not window._v1_busy()),
        timeout=7000,
    )


def scan(qtbot, window):
    qtbot.waitUntil(lambda: not window.game_center.busy)
    window.game_center.poll()
    qtbot.waitUntil(lambda: not window.game_center.busy)


def test_actual_game_mode_and_saved_base_mode_stay_distinct(integrated, qtbot):
    window, api = integrated
    assert window.settings.language == "ru"
    api.names = ["game.exe"]
    scan(qtbot, window)
    assert window._effective_profile == "Gaming"
    assert window.profile_combo.currentData() == "Gaming"
    assert window.store.load().profile == "Maximum AI"
    window.profile_combo.setCurrentIndex(window.profile_combo.findData("Eco"))
    assert window.store.load().profile == "Eco"
    assert window._effective_profile == "Gaming"
    assert window.profile_combo.currentData() == "Gaming"
    api.names = []
    scan(qtbot, window)
    assert window._effective_profile == "Eco"
    assert window.profile_combo.currentData() == "Eco"


def test_real_chat_completion_marks_only_nexus_model_for_worker_unload(integrated, qtbot):
    window, api = integrated
    window.refresh_models()
    qtbot.waitUntil(lambda: not window._jobs and not window._pool.activeThreadCount())
    window.prompt.setPlainText("Привет")
    window.send_message()
    qtbot.waitUntil(
        lambda: (
            not window._jobs
            and not window._pool.activeThreadCount()
            and not window.conversations.busy
        )
    )
    assert window.game_center.controller.owned_model == "owned:latest"
    api.names = ["game.exe"]
    scan(qtbot, window)
    assert api.unloaded == ["owned:latest"]
    assert "unrelated:latest" not in api.unloaded
    assert all(identity != threading.get_ident() for identity in api.threads)
    assert window.store.load().profile == "Maximum AI"
    api.names = []
    scan(qtbot, window)
    assert window._effective_profile == "Maximum AI"


def test_model_discovery_does_not_grant_unload_ownership(integrated, qtbot):
    window, api = integrated
    window.refresh_models()
    qtbot.waitUntil(lambda: not window._jobs and not window._pool.activeThreadCount())
    api.names = ["game.exe"]
    scan(qtbot, window)
    assert window._effective_profile == "Gaming"
    assert api.unloaded == []
    assert window.game_center.controller.owned_model is None
