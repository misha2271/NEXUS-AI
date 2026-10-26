from __future__ import annotations

import json
from dataclasses import replace

import pytest

from nexus_ai import settings as settings_module
from nexus_ai.settings import Settings, SettingsStore, default_settings_path, validate_settings


def test_missing_file_uses_defaults_without_creating_file(tmp_path):
    store = SettingsStore(tmp_path / "nested" / "settings.json")
    assert store.load() == Settings()
    assert store.warning is None
    assert not store.path.exists()


def test_settings_round_trip_normalizes_values(tmp_path):
    store = SettingsStore(tmp_path / "nested" / "settings.json")
    store.save(Settings("https://localhost:11434/ollama///", " qwen3:8b ", "Gaming"))
    assert store.load() == Settings("https://localhost:11434/ollama", "qwen3:8b", "Gaming")
    assert json.loads(store.path.read_text(encoding="utf-8"))["profile"] == "Gaming"
    assert list(store.path.parent.glob("*.tmp")) == []


@pytest.mark.parametrize("contents", ["{not json", "[]", "null", "\xff"])
def test_corrupt_settings_preserved_with_warning(tmp_path, contents):
    path = tmp_path / "settings.json"
    path.write_text(contents, encoding="utf-8")
    store = SettingsStore(path)
    assert store.load() == Settings()
    assert store.warning
    assert path.read_text(encoding="utf-8") == contents


def test_invalid_fields_default_independently(tmp_path):
    path = tmp_path / "settings.json"
    data = {"ollama_url": "ftp://example.test", "model": "llama3.2:3b", "profile": "turbo"}
    path.write_text(json.dumps(data), encoding="utf-8")
    store = SettingsStore(path)
    assert store.load() == Settings(model="llama3.2:3b")
    assert "ollama_url" in store.warning
    assert "profile" in store.warning
    assert json.loads(path.read_text(encoding="utf-8")) == data


def test_invalid_utf8_settings_preserved(tmp_path):
    path = tmp_path / "settings.json"
    path.write_bytes(b"\xff\xfe")
    store = SettingsStore(path)
    assert store.load() == Settings()
    assert store.warning
    assert path.read_bytes() == b"\xff\xfe"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "localhost:11434",
        "ftp://localhost",
        "http:///no-host",
        "http://user:secret@localhost",
        "http://localhost/?token=secret",
        "http://localhost/#fragment",
        "http://local host",
        "http://localhost/?",
        "http://localhost/#",
        "http://localhost:invalid",
        "http://localhost:65536",
        "http://localhost:0",
        "http://[broken",
        "http://local\nhost",
        "http://local\\host",
        "http://local\x7fhost",
        12,
        None,
    ],
)
def test_invalid_urls_rejected(url):
    with pytest.raises(ValueError):
        validate_settings(replace(Settings(), ollama_url=url))


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:11434", "https://example.test/ollama", "http://[::1]:11434"]
)
def test_valid_local_and_remote_urls(url):
    assert validate_settings(replace(Settings(), ollama_url=url)).ollama_url == url


@pytest.mark.parametrize(
    "field,value",
    [("model", None), ("model", "model\x00name"), ("profile", "unknown"), ("profile", [])],
)
def test_invalid_explicit_values_rejected(field, value):
    with pytest.raises(ValueError):
        validate_settings(replace(Settings(), **{field: value}))


def test_failed_replace_keeps_previous_settings_and_cleans_temp(tmp_path, monkeypatch):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(Settings(model="old"))

    def fail_replace(*_args):
        raise PermissionError("file is busy")

    monkeypatch.setattr(settings_module.os, "replace", fail_replace)
    with pytest.raises(PermissionError):
        store.save(Settings(model="new"))
    assert store.load().model == "old"
    assert len(list(tmp_path.iterdir())) == 1


def test_invalid_save_preserves_previous_file(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(Settings(model="old"))
    with pytest.raises(ValueError):
        store.save(Settings(profile="unknown"))
    assert store.load() == Settings(model="old")


def test_default_windows_path_uses_appdata(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert default_settings_path() == tmp_path / "NEXUS AI" / "settings.json"


def test_default_linux_path_uses_xdg(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_settings_path() == tmp_path / "nexus-ai" / "settings.json"


def test_unknown_keys_allow_forward_compatible_load(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"model": "qwen3:8b", "future": true}', encoding="utf-8")
    store = SettingsStore(path)
    assert store.load() == Settings(model="qwen3:8b")
    assert store.warning is None
