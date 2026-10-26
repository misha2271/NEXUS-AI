"""Check frozen-runtime path rules; these are not native Windows build tests."""

from __future__ import annotations

from types import SimpleNamespace

import nexus_ai.settings as settings_module
from nexus_ai.settings import Settings, SettingsStore


def test_frozen_settings_survive_executable_extraction_and_working_directory_changes(
    monkeypatch, tmp_path
):
    appdata = tmp_path / "profile" / "Roaming"
    first_install = tmp_path / "install-one"
    first_extract = tmp_path / "_MEI-first"
    first_working = tmp_path / "documents"
    for directory in (first_install, first_extract, first_working):
        directory.mkdir()
    # Substitute this module's runtime view, without changing pytest's host platform.
    runtime = SimpleNamespace(
        platform="win32",
        frozen=True,
        executable=str(first_install / "NEXUS-AI.exe"),
        _MEIPASS=str(first_extract),
    )
    monkeypatch.setattr(settings_module, "sys", runtime)
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.chdir(first_working)
    store = SettingsStore()
    expected = appdata / "NEXUS AI" / "settings.json"
    assert store.path == expected
    preferences = Settings(ollama_url="http://localhost:11434", model="tiny:latest", profile="Eco")
    store.save(preferences)

    second_install = tmp_path / "install-two"
    second_extract = tmp_path / "_MEI-second"
    second_working = tmp_path / "downloads"
    for directory in (second_install, second_extract, second_working):
        directory.mkdir()
    runtime.executable = str(second_install / "NEXUS-AI.exe")
    runtime._MEIPASS = str(second_extract)
    monkeypatch.chdir(second_working)
    reopened = SettingsStore()
    assert reopened.path == expected
    assert reopened.load() == preferences
    assert reopened.warning is None
    assert not list(appdata.rglob(".settings-*.tmp"))
    for directory in (
        first_install,
        first_extract,
        first_working,
        second_install,
        second_extract,
        second_working,
    ):
        assert list(directory.iterdir()) == []


def test_windows_settings_fallback_is_user_roaming_folder(monkeypatch, tmp_path):
    user_home = tmp_path / "user-home"
    monkeypatch.setattr(settings_module, "sys", SimpleNamespace(platform="win32", frozen=True))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(settings_module.Path, "home", lambda: user_home)
    store = SettingsStore()
    assert store.path == user_home / "AppData" / "Roaming" / "NEXUS AI" / "settings.json"


def test_explicit_settings_path_remains_respected_in_frozen_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_module, "sys", SimpleNamespace(platform="win32", frozen=True))
    monkeypatch.setenv("APPDATA", str(tmp_path / "profile"))
    path = tmp_path / "isolated" / "probe.json"
    store = SettingsStore(path)
    store.save(Settings(profile="Gaming"))
    assert store.path == path
    assert store.load().profile == "Gaming"
    assert not (tmp_path / "profile").exists()
