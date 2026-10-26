"""Validated, atomic JSON settings stored in the user's configuration directory."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from nexus_ai.i18n import LANGUAGES, Text
from nexus_ai.profiles import PROFILE_NAMES


@dataclass(frozen=True)
class Settings:
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = ""
    profile: str = "Smart"
    language: str = "ru"


def _normalize_url(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(Text("Ollama URL must be text."))
    value = value.strip()
    if not value or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(Text("Ollama URL must not contain whitespace or control characters."))
    if "\\" in value:
        raise ValueError(Text("Ollama URL must not contain backslashes."))
    try:
        parsed = urlsplit(value)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError as exc:
        raise ValueError(Text("Ollama URL contains an invalid hostname or port.")) from exc
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValueError(Text("Ollama URL must be an HTTP or HTTPS URL with a hostname."))
    if port is not None and not 1 <= port <= 65535:
        raise ValueError(Text("Ollama URL port must be between 1 and 65535."))
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(Text("Ollama URL must not contain embedded credentials."))
    if "?" in value or "#" in value:
        raise ValueError(Text("Ollama URL must not contain a query or fragment."))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def validate_settings(settings: Settings) -> Settings:
    """Return normalized settings, or reject an invalid explicit user update."""
    url = _normalize_url(settings.ollama_url)
    if not isinstance(settings.model, str):
        raise ValueError(Text("Model name must be text."))
    model = settings.model.strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in model):
        raise ValueError(Text("Model name must not contain control characters."))
    if settings.profile not in PROFILE_NAMES:
        raise ValueError(Text("Choose a supported performance profile."))
    if settings.language not in LANGUAGES:
        raise ValueError(Text("Choose Russian or English."))
    return Settings(
        ollama_url=url, model=model, profile=settings.profile, language=settings.language
    )


def default_settings_path() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return root / "NEXUS AI" / "settings.json"
    root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return root / "nexus-ai" / "settings.json"


class SettingsStore:
    """Recover invalid settings in memory, preserving the original file on load."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_settings_path()
        self.warning: str | None = None

    def load(self) -> Settings:
        self.warning = None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Settings()
        except (OSError, UnicodeError, json.JSONDecodeError):
            self.warning = (
                "Settings could not be read; defaults are in use. The file was preserved."
            )
            return Settings()
        if not isinstance(data, dict):
            self.warning = (
                "Settings must be a JSON object; defaults are in use. The file was preserved."
            )
            return Settings()
        settings = Settings()
        invalid_fields: list[str] = []
        for field in ("ollama_url", "model", "profile", "language"):
            if field not in data:
                continue
            try:
                settings = validate_settings(replace(settings, **{field: data[field]}))
            except ValueError:
                invalid_fields.append(field)
        if invalid_fields:
            self.warning = Text(
                "Invalid settings reset to defaults: {fields}. The file was preserved.",
                fields=", ".join(invalid_fields),
            )
        return settings

    def save(self, settings: Settings) -> None:
        settings = validate_settings(settings)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".settings-",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary = Path(file.name)
                json.dump(asdict(settings), file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
            self.warning = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
