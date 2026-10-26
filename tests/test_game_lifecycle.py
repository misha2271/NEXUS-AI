"""Tests use synthetic process lists; never start games or unload a model."""

from __future__ import annotations

from types import SimpleNamespace

import psutil
import pytest

from nexus_ai.game_lifecycle import (
    GameGuard,
    configured_games,
    normalize_executable,
    running_games,
)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        " ",
        "../game.exe",
        "C:\\Games\\game.exe",
        "game",
        "*.exe",
        "game.exe --flag",
        ".exe",
        "x" * 130 + ".exe",
    ],
)
def test_only_executable_filenames_are_allowed(bad):
    with pytest.raises(ValueError):
        normalize_executable(bad)


def test_names_are_case_insensitive_and_explicit():
    assert configured_games(["HogwartsLegacy.exe", "hogwartslegacy.EXE"]) == {
        "hogwartslegacy.exe"
    }
    assert normalize_executable("HogwartsLegacy.exe") == "hogwartslegacy.exe"


def test_detector_matches_only_configured_process_names():
    def fake_iter(**kwargs):
        assert kwargs == {"attrs": ["name"], "ad_value": None}
        return iter(
            [
                SimpleNamespace(info={"name": "HogwartsLegacy.EXE"}),
                SimpleNamespace(info={"name": "python.exe"}),
                SimpleNamespace(info={"name": None}),
                SimpleNamespace(info={"name": "chrome.exe"}),
            ]
        )

    assert running_games(["HogwartsLegacy.exe"], process_iter=fake_iter) == {
        "hogwartslegacy.exe"
    }


def test_detector_skips_inaccessible_processes():
    class Inaccessible:
        @property
        def info(self):
            raise psutil.AccessDenied(pid=123)

    def fake_iter(**_):
        return iter([Inaccessible(), SimpleNamespace(info={"name": "Game.exe"})])

    assert running_games(["game.exe"], process_iter=fake_iter) == {"game.exe"}


def test_detector_empty_config_never_scans():
    def fail(**_):
        pytest.fail("Should not scan when no games are configured")

    assert not running_games([], process_iter=fail)


def test_game_transitions_do_not_assume_process_is_a_game():
    guard = GameGuard(["HogwartsLegacy.exe"])
    assert not guard.observe(["explorer.exe"]).game_started
    first = guard.observe(["HogwartsLegacy.exe"])
    assert first.game_started
    assert first.unload_model is None
    assert not guard.observe(["HogwartsLegacy.exe"]).game_started
    last = guard.observe([])
    assert last.game_finished


def test_unload_requires_opt_in_and_explicitly_recorded_nexus_model():
    guard = GameGuard(["Game.exe"])
    assert guard.observe(["Game.exe"], allow_unload=True).unload_model is None
    guard.observe([])
    guard.remember_nexus_model("qwen3:8b")
    assert guard.observe(["Game.exe"], allow_unload=False).unload_model is None
    guard.observe([])
    assert guard.observe(["Game.exe"], allow_unload=True).unload_model == "qwen3:8b"
    assert guard.observe(["Game.exe"], allow_unload=True).unload_model is None


def test_multiple_games_only_start_once_until_all_exit():
    guard = GameGuard(["One.exe", "Two.exe"])
    assert guard.observe(["One.exe"]).game_started
    middle = guard.observe(["Two.exe"])
    assert not middle.game_started and not middle.game_finished
    assert guard.observe([]).game_finished


def test_game_exit_does_not_preload_models():
    guard = GameGuard(["Game.exe"])
    guard.remember_nexus_model("qwen3:8b")
    guard.observe(["Game.exe"], allow_unload=True)
    result = guard.observe([], allow_unload=True)
    assert result.game_finished and result.unload_model is None
