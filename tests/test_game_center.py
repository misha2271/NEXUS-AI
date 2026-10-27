"""Game Guard GUI integration uses actual worker scheduling with isolated fixtures."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from nexus_ai.gaming import GameConfiguration, GameProfile, GameProfileStore, ProcessDetector
from nexus_ai.ui.game_center import GameCenter
from nexus_ai.ui.localization import Translator


class Fixture:
    def __init__(self):
        self.names = []
        self.calls = []
        self.threads = []
        self.failure = False

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

            def unload_model(self, model):
                fixture.calls.append(("unload", url, model))
                if fixture.failure:
                    raise RuntimeError("server rejected operation")

            def load_model(self, model):
                fixture.calls.append(("load", url, model))

        return Client()


@pytest.fixture
def make_center(qtbot, tmp_path):
    centers = []

    def make(config=None, base_mode="Maximum AI"):
        config = config if config is not None else GameConfiguration()
        path = tmp_path / str(len(centers)) / "settings.json"
        GameProfileStore(path.with_name("games.json")).save(config)
        fixture = Fixture()
        translator = Translator("en")
        center = GameCenter(
            translator,
            path,
            base_mode=base_mode,
            client_factory=fixture.client,
            detector=ProcessDetector(fixture.processes),
        )
        center._translator_keepalive = translator
        centers.append(center)
        qtbot.addWidget(center)
        center.start()
        qtbot.waitUntil(lambda: not center.busy)
        return center, fixture

    yield make
    for center in centers:
        center.shutdown()
        qtbot.waitUntil(lambda center=center: not center.busy)


def scan(qtbot, center):
    qtbot.waitUntil(lambda: not center.busy)
    center.poll()
    qtbot.waitUntil(lambda: not center.busy)


def test_add_remove_and_opt_in_preferences_are_persisted(make_center, qtbot):
    center, fixture = make_center()
    assert not center.enable.isChecked()
    assert not center.allow_unload.isChecked()
    center.name_input.setText("Моя игра")
    center.executables_input.setText("GAME.EXE; helper.exe")
    center.add_button.click()
    qtbot.waitUntil(lambda: not center.busy)
    stored = center.store.load()
    assert stored.profiles == (GameProfile("Моя игра", ("game.exe", "helper.exe")),)
    assert not stored.profiles[0].unload_model
    center.games.setCurrentRow(0)
    center.executables_input.setText("new.exe")
    center.update_button.click()
    qtbot.waitUntil(lambda: not center.busy)
    assert center.store.load().profiles[0].executables == ("new.exe",)
    center.enable.setChecked(True)
    qtbot.waitUntil(lambda: not center.busy)
    assert center.store.load().enabled
    center.games.setCurrentRow(0)
    center.remove_button.click()
    qtbot.waitUntil(lambda: not center.busy)
    assert center.store.load().profiles == ()
    assert not fixture.calls


def test_game_launch_defers_unload_and_exit_restores_previous_profile(make_center, qtbot):
    config = GameConfiguration(True, (GameProfile("Example", ("game.exe",), "Gaming", True),))
    center, fixture = make_center(config)
    modes = []
    center.effective_profile.connect(modes.append)
    center.note_model_used("nexus-owned")
    center.set_chat_busy(True)
    fixture.names = ["GAME.EXE", "unrelated.exe"]
    scan(qtbot, center)
    assert modes == ["Gaming"]
    assert fixture.calls == []
    center.set_chat_busy(False)
    qtbot.waitUntil(lambda: not center.busy)
    assert fixture.calls == [("unload", "http://127.0.0.1:11434", "nexus-owned")]
    scan(qtbot, center)
    assert len(fixture.calls) == 1
    fixture.names = []
    scan(qtbot, center)
    assert modes == ["Gaming", "Maximum AI"]
    assert len(fixture.calls) == 1  # no eager reload when a game exits
    assert all(identity != threading.get_ident() for identity in fixture.threads)


def test_unowned_models_and_non_opted_in_models_are_not_unloaded(make_center, qtbot):
    config = GameConfiguration(True, (GameProfile("Example", ("game.exe",)),))
    center, fixture = make_center(config)
    fixture.names = ["game.exe"]
    scan(qtbot, center)
    center.note_model_used("one")
    scan(qtbot, center)
    assert not fixture.calls


def test_restore_on_demand_and_server_change_forget_ownership(make_center, qtbot):
    config = GameConfiguration(True, (GameProfile("Example", ("game.exe",), "Gaming", True),))
    center, fixture = make_center(config)
    center.note_model_used("one")
    fixture.names = ["game.exe"]
    scan(qtbot, center)
    assert fixture.calls[-1][0] == "unload"
    center.restore_button.click()
    qtbot.waitUntil(lambda: not center.busy)
    assert fixture.calls[-1][0] == "load"
    scan(qtbot, center)
    assert len(fixture.calls) == 2  # explicit restoration is not immediately undone
    center.set_endpoint("http://localhost:9999")
    assert center.controller.owned_model is None
    scan(qtbot, center)
    assert len(fixture.calls) == 2


def test_invalid_game_does_not_replace_existing_configuration(make_center):
    center, _ = make_center()
    center.name_input.setText("unsafe")
    center.executables_input.setText("../game.exe")
    center.add_button.click()
    assert center.config.profiles == ()
    assert "basenames" in center.status.text()


def test_failed_unload_does_not_retry_every_poll(make_center, qtbot):
    config = GameConfiguration(True, (GameProfile("Example", ("game.exe",), "Gaming", True),))
    center, fixture = make_center(config)
    center.note_model_used("one")
    fixture.failure = True
    fixture.names = ["game.exe"]
    scan(qtbot, center)
    scan(qtbot, center)
    assert len(fixture.calls) == 1


def test_shutdown_does_not_schedule_more_scans(make_center, qtbot):
    center, fixture = make_center()
    center.shutdown()
    center.poll()
    center.start()
    assert not center.busy
    assert not fixture.calls


def test_russian_game_actions_reflow_without_imposing_wide_minimum(qtbot, tmp_path):
    translator = Translator("ru")
    center = GameCenter(translator, tmp_path / "settings.json")
    qtbot.addWidget(center)
    center.resize(420, 550)
    center.show()
    qtbot.waitUntil(lambda: center.actions.columns == 1)
    assert center.width() == 420
    for button in center.actions.widgets:
        assert button.geometry().right() <= center.actions.width()
    center.resize(700, 550)
    qtbot.waitUntil(lambda: center.actions.columns == 2)
    center.resize(1100, 550)
    qtbot.waitUntil(lambda: center.actions.columns == 4)
    center.shutdown()
