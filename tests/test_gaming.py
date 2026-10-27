"""Configured process detection and durable opt-in game profiles."""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import psutil
import pytest

from nexus_ai.gaming import (
    GameConfiguration,
    GameProfile,
    GameProfileStore,
    ProcessDetector,
    validate_configuration,
)


def profile(**values):
    return replace(GameProfile("Моя игра", ("Example.EXE",)), **values)


def test_default_detection_is_opt_in_and_performs_no_enumeration(tmp_path):
    store = GameProfileStore(tmp_path / "games.json")
    assert store.load() == GameConfiguration()
    assert not store.path.exists()
    detector = ProcessDetector(lambda **_: pytest.fail("disabled enumeration"))
    result = detector.scan(GameConfiguration())
    assert result.active is None and result.complete
    assert "disabled" in result.status


def test_profile_store_roundtrip_preserves_all_modes_priority_and_unicode(tmp_path):
    store = GameProfileStore(tmp_path / "nested" / "games.json")
    profiles = tuple(
        profile(name=name, mode=name, priority=index - 2)
        for index, name in enumerate(("Smart", "Gaming", "Maximum AI", "Eco"))
    )
    config = GameConfiguration(True, profiles)
    store.save(config)
    loaded = store.load()
    assert loaded == validate_configuration(config)
    assert loaded.profiles[0].executables == ("example.exe",)
    assert store.warning is None
    assert json.loads(store.path.read_text(encoding="utf-8"))["enabled"] is True
    assert not list(store.path.parent.glob(".games-*.tmp"))


@pytest.mark.parametrize(
    "contents",
    [b"{", b"[]", b"null", b"\xff", b"x" * (256 * 1024 + 1)],
    ids=["malformed-json", "json-array", "json-null", "invalid-utf8", "oversized-file"],
)
def test_corrupt_or_oversized_profile_file_preserved_and_detection_disabled(tmp_path, contents):
    path = tmp_path / "games.json"
    path.write_bytes(contents)
    store = GameProfileStore(path)
    assert store.load() == GameConfiguration()
    assert store.warning
    assert path.read_bytes() == contents


@pytest.mark.parametrize(
    "data",
    [
        {"enabled": "yes"},
        {"enabled": True, "profiles": [None]},
        {"enabled": True, "profiles": [{"name": "game", "executables": ["../evil.exe"]}]},
        {
            "enabled": True,
            "profiles": [{"name": "game", "executables": ["game.exe"], "mode": "turbo"}],
        },
        {
            "enabled": True,
            "profiles": [{"name": "game", "executables": ["game.exe"], "priority": True}],
        },
    ],
)
def test_invalid_profile_configuration_is_never_partially_enabled(tmp_path, data):
    path = tmp_path / "games.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    store = GameProfileStore(path)
    assert not store.load().enabled
    assert store.warning
    assert json.loads(path.read_text(encoding="utf-8")) == data


@pytest.mark.parametrize(
    "changes",
    [
        {"name": ""},
        {"name": "bad\nname"},
        {"mode": "turbo"},
        {"mode": []},
        {"priority": True},
        {"priority": 101},
        {"unload_model": 1},
        {"executables": ()},
        {"executables": "game.exe"},
        {"executables": ("..",)},
        {"executables": ("C:\\game.exe",)},
        {"executables": ("folder/game.exe",)},
        {"executables": ("*.exe",)},
        {"executables": ("game?.exe",)},
        {"executables": (" game.exe",)},
        {"executables": ("game.exe\n",)},
    ],
)
def test_profile_validation_rejects_invalid_modes_paths_wildcards_and_types(changes):
    with pytest.raises(ValueError):
        validate_configuration(GameConfiguration(True, (profile(**changes),)))


def test_duplicate_names_rejected_and_duplicate_process_names_normalized():
    with pytest.raises(ValueError, match="unique"):
        validate_configuration(GameConfiguration(True, (profile(), profile(name="МОЯ ИГРА"))))
    config = validate_configuration(
        GameConfiguration(True, (profile(executables=("Game.EXE", "game.exe")),))
    )
    assert config.profiles[0].executables == ("game.exe",)


def test_failed_atomic_save_keeps_previous_file(tmp_path, monkeypatch):
    import nexus_ai.gaming as gaming

    store = GameProfileStore(tmp_path / "games.json")
    store.save(GameConfiguration())
    original = store.path.read_bytes()

    def fail(*_):
        raise PermissionError("file locked")

    monkeypatch.setattr(gaming.os, "replace", fail)
    with pytest.raises(PermissionError):
        store.save(GameConfiguration(True, (profile(),)))
    assert store.path.read_bytes() == original
    assert not list(tmp_path.glob(".games-*.tmp"))


def test_exact_case_insensitive_matches_and_priority_do_not_guess_game_names():
    calls = []

    def processes(**kwargs):
        calls.append(kwargs)
        return [
            SimpleNamespace(info={"name": name})
            for name in ("EXAMPLE.EXE", "another.exe", "example.exe.launcher", "System")
        ]

    game = profile()
    priority = profile(name="Another", executables=("ANOTHER.exe",), priority=3, mode="Eco")
    detector = ProcessDetector(processes)
    result = detector.scan(GameConfiguration(True, (game, priority)))
    assert result.active.name == "Another"
    assert result.active.mode == "Eco"
    assert result.matched_processes == ("another.exe",)
    assert result.complete
    assert calls == [{"attrs": ["name"]}]
    assert (
        detector.scan(GameConfiguration(True, (profile(executables=("EXAMP.exe",)),))).active
        is None
    )


def test_equal_priority_uses_explicit_file_order():
    detector = ProcessDetector(lambda **_: [SimpleNamespace(info={"name": "example.exe"})])
    first = profile(name="First")
    second = profile(name="Second")
    result = detector.scan(GameConfiguration(True, (first, second)))
    assert result.active.name == "First"


def test_inaccessible_process_does_not_invent_a_match_or_prove_game_exit():
    class Protected:
        @property
        def info(self):
            raise psutil.AccessDenied(99)

    detector = ProcessDetector(lambda **_: [Protected(), SimpleNamespace(info={"name": None})])
    result = detector.scan(GameConfiguration(True, (profile(),)))
    assert result.active is None and not result.complete
    assert not result.matched_processes
    assert "incomplete" in result.status


def test_vanished_process_can_be_ignored_but_enumeration_failure_is_incomplete():
    class Gone:
        @property
        def info(self):
            raise psutil.NoSuchProcess(123)

    detector = ProcessDetector(lambda **_: [Gone()])
    assert detector.scan(GameConfiguration(True, (profile(),))).complete

    def denied(**_):
        raise psutil.AccessDenied(1)

    result = ProcessDetector(denied).scan(GameConfiguration(True, (profile(),)))
    assert not result.complete and result.active is None


def test_empty_profiles_do_not_enumerate_processes():
    result = ProcessDetector(lambda **_: pytest.fail("unexpected enumeration")).scan(
        GameConfiguration(True)
    )
    assert result.active is None and "Add executable" in result.status


def test_known_game_exit_can_be_confirmed_despite_unrelated_protected_process():
    from nexus_ai.lifecycle import LifecycleController

    class IdentifiedGame:
        info = {"name": "example.exe"}
        running = True

        def is_running(self):
            return self.running

    class Protected:
        @property
        def info(self):
            raise psutil.AccessDenied(4)

    game = IdentifiedGame()
    processes = [game, Protected()]
    detector = ProcessDetector(lambda **_: processes)
    controller = LifecycleController("Maximum AI")
    config = GameConfiguration(True, (profile(),))
    first = detector.scan(config)
    assert first.active is not None and not first.complete
    assert controller.observe(first).mode == "Gaming"
    processes[:] = [Protected()]
    still_running = detector.scan(config)
    assert not still_running.confirmed_exit
    assert controller.observe(still_running).mode == "Gaming"
    game.running = False
    exited = detector.scan(config)
    assert not exited.complete and exited.confirmed_exit
    assert controller.observe(exited).mode == "Maximum AI"


def test_known_game_access_error_never_proves_exit():
    class IdentifiedGame:
        info = {"name": "example.exe"}

        def is_running(self):
            raise psutil.AccessDenied(10)

    game = IdentifiedGame()
    processes = [game]
    detector = ProcessDetector(lambda **_: processes)
    config = GameConfiguration(True, (profile(),))
    assert detector.scan(config).active is not None
    processes[:] = [SimpleNamespace(info={"name": None})]
    assert not detector.scan(config).confirmed_exit


def test_process_iterator_failure_does_not_claim_tracked_game_exit():
    class IdentifiedGame:
        info = {"name": "example.exe"}

        def is_running(self):
            return False

    fail = False

    def processes(**_):
        if fail:
            raise OSError("enumeration unavailable")
        return [IdentifiedGame()]

    detector = ProcessDetector(processes)
    config = GameConfiguration(True, (profile(),))
    assert detector.scan(config).active is not None
    fail = True
    assert not detector.scan(config).confirmed_exit


def test_removed_game_does_not_remain_in_tracked_session():
    class Game:
        def __init__(self, name):
            self.info = {"name": name}
            self.running = True

        def is_running(self):
            return self.running

    first, second = Game("first.exe"), Game("second.exe")
    protected = SimpleNamespace(info={"name": None})
    processes = [first, protected]
    detector = ProcessDetector(lambda **_: processes)
    config = GameConfiguration(True, (profile(executables=("first.exe",)),))
    assert detector.scan(config).active is not None
    config = GameConfiguration(True, (profile(executables=("second.exe",)),))
    processes[:] = [second, protected]
    assert detector.scan(config).active is not None
    processes[:] = [protected]
    second.running = False
    # An unconfigured old game still running must not keep the new session active.
    assert first.running and detector.scan(config).confirmed_exit
