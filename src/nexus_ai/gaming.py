"""Persistent, explicitly configured game detection through real process names.

No game list is guessed, no process is killed, and inaccessible processes do not
count as evidence that a game ended. Call process enumeration off the UI thread.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import psutil

from nexus_ai.i18n import Text
from nexus_ai.profiles import PROFILE_NAMES
from nexus_ai.settings import default_settings_path

_MAX_FILE_BYTES = 256 * 1024


@dataclass(frozen=True)
class GameProfile:
    name: str
    executables: tuple[str, ...]
    mode: str = "Gaming"
    unload_model: bool = False
    priority: int = 0


@dataclass(frozen=True)
class GameConfiguration:
    enabled: bool = False
    profiles: tuple[GameProfile, ...] = ()


def validate_configuration(config: GameConfiguration) -> GameConfiguration:
    if not isinstance(config, GameConfiguration):
        raise ValueError(Text("Game detection configuration is invalid."))
    if type(config.enabled) is not bool or not isinstance(config.profiles, (tuple, list)):
        raise ValueError(Text("Game detection configuration is invalid."))
    if len(config.profiles) > 100:
        raise ValueError(Text("At most 100 game profiles are supported."))
    profiles: list[GameProfile] = []
    names: set[str] = set()
    for profile in config.profiles:
        if not isinstance(profile, GameProfile):
            raise ValueError(Text("Game profile is invalid."))
        name = profile.name.strip() if isinstance(profile.name, str) else ""
        if not name or len(name) > 120 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise ValueError(Text("Game profile needs a valid name."))
        if name.casefold() in names:
            raise ValueError(Text("Game profile names must be unique."))
        names.add(name.casefold())
        if profile.mode not in PROFILE_NAMES or type(profile.unload_model) is not bool:
            raise ValueError(Text("Game profile mode or unload preference is invalid."))
        if type(profile.priority) is not int or not -100 <= profile.priority <= 100:
            raise ValueError(Text("Game profile priority must be between -100 and 100."))
        if (
            not isinstance(profile.executables, (tuple, list))
            or not 1 <= len(profile.executables) <= 32
        ):
            raise ValueError(Text("Specify between 1 and 32 executable names per game profile."))
        executables: list[str] = []
        for executable in profile.executables:
            if (
                not isinstance(executable, str)
                or not executable
                or executable != executable.strip()
                or len(executable) > 255
                or executable in {".", ".."}
                or any(c in executable for c in "/\\:*?[]")
                or any(ord(c) < 32 or ord(c) == 127 for c in executable)
            ):
                raise ValueError(Text("Use exact executable basenames, not paths or wildcards."))
            canonical = executable.casefold()
            if canonical not in executables:
                executables.append(canonical)
        profiles.append(
            GameProfile(
                name, tuple(executables), profile.mode, profile.unload_model, profile.priority
            )
        )
    return GameConfiguration(config.enabled, tuple(profiles))


class GameProfileStore:
    """Atomic user configuration; failed/corrupt loads never enable detection."""

    def __init__(self, path: Path | None = None):
        self.path = (
            Path(path) if path is not None else default_settings_path().with_name("games.json")
        )
        self.warning: str | None = None

    def load(self) -> GameConfiguration:
        self.warning = None
        try:
            with self.path.open("rb") as handle:
                data = handle.read(_MAX_FILE_BYTES + 1)
            if len(data) > _MAX_FILE_BYTES:
                raise ValueError("oversized configuration")
            raw = json.loads(data.decode("utf-8"))
            if not isinstance(raw, dict) or not isinstance(raw.get("profiles", []), list):
                raise ValueError("invalid configuration")
            profiles = []
            for item in raw.get("profiles", []):
                if not isinstance(item, dict):
                    raise ValueError("invalid profile")
                profiles.append(
                    GameProfile(
                        name=item.get("name"),
                        executables=item.get("executables"),
                        mode=item.get("mode", "Gaming"),
                        unload_model=item.get("unload_model", False),
                        priority=item.get("priority", 0),
                    )
                )
            return validate_configuration(
                GameConfiguration(raw.get("enabled", False), tuple(profiles))
            )
        except FileNotFoundError:
            return GameConfiguration()
        except (OSError, ValueError, TypeError):
            self.warning = Text(
                "Game profiles could not be read. Detection is disabled; the file was preserved."
            )
            return GameConfiguration()

    def save(self, config: GameConfiguration) -> None:
        normalized = validate_configuration(config)
        encoded = json.dumps(asdict(normalized), ensure_ascii=False, indent=2) + "\n"
        if len(encoded.encode("utf-8")) > _MAX_FILE_BYTES:
            raise ValueError(Text("Game profile configuration is too large."))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".games-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self.warning = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class GameDetection:
    active: GameProfile | None
    matched_processes: tuple[str, ...]
    complete: bool
    status: str
    confirmed_exit: bool = False


class ProcessDetector:
    def __init__(self, process_iter: Callable = psutil.process_iter):
        self._process_iter = process_iter
        self._known_games: tuple = ()
        self._known_configuration = None

    def _known_games_exited(self) -> bool:
        """psutil's identity-aware is_running checks PID reuse as well as existence.

        Never query unknown protected processes to guess whether they are games.
        A previous positively identified game session may nevertheless be proven
        finished even if unrelated Windows system process names are inaccessible.
        """
        if not self._known_games:
            return False
        try:
            return all(not process.is_running() for process in self._known_games)
        except (psutil.Error, OSError, AttributeError):
            return False

    def scan(self, config: GameConfiguration) -> GameDetection:
        config = validate_configuration(config)
        if config != self._known_configuration:
            self._known_games = ()
            self._known_configuration = config
        if not config.enabled:
            self._known_games = ()
            return GameDetection(None, (), True, Text("Automatic game detection is disabled."))
        if not config.profiles:
            self._known_games = ()
            return GameDetection(
                None, (), True, Text("Add executable names to enable game detection.")
            )
        observed: set[str] = set()
        known_games = []
        requested = {name for profile in config.profiles for name in profile.executables}
        complete = True
        enumeration_finished = True
        try:
            for process in self._process_iter(attrs=["name"]):
                try:
                    name = process.info.get("name")
                    if isinstance(name, str) and name:
                        observed.add(name.casefold())
                        if name.casefold() in requested:
                            known_games.append(process)
                    else:
                        # Unknown/denied process names cannot establish that a game ended.
                        complete = False
                except psutil.NoSuchProcess:
                    continue
                except (psutil.AccessDenied, OSError, AttributeError):
                    complete = False
        except (psutil.Error, OSError):
            complete = False
            enumeration_finished = False
        candidates = [
            (profile, tuple(name for name in profile.executables if name in observed))
            for profile in config.profiles
        ]
        matching = [(profile, names) for profile, names in candidates if names]
        if matching:
            if not complete:
                # Keep already identified concurrent games when a later scan
                # cannot read their names; do not forget a hidden active game.
                known_games.extend(
                    process for process in self._known_games if process not in known_games
                )
            self._known_games = tuple(known_games)
            # Stable file order resolves equal priorities deterministically.
            profile, processes = max(matching, key=lambda item: item[0].priority)
            return GameDetection(
                profile, processes, complete, Text("Game detected: {game}", game=profile.name)
            )
        confirmed_exit = enumeration_finished and self._known_games_exited()
        if complete or confirmed_exit:
            self._known_games = ()
        status = (
            Text("No configured game process is running.")
            if complete
            else Text("Process detection is incomplete; some process names are inaccessible.")
        )
        return GameDetection(None, (), complete, status, confirmed_exit)
