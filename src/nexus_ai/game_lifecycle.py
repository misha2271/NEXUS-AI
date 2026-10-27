"""Explicit game detection and opt-in Ollama model lifecycle decisions.

This module NEVER closes a process, writes to a device or executes an unload
request. Callers must separately authorize, schedule and perform an Ollama
request. Ollama is shared: unloading a model may affect other Ollama clients.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import psutil


def normalize_executable(name: str) -> str:
    """Accept an executable NAME, not a path, wildcard, command or process ID."""
    if not isinstance(name, str):
        raise ValueError("Expected a game executable name.")
    name = name.strip()
    if (
        len(name) > 128
        or not re.fullmatch(r"[\w][\w .()+-]*\.exe", name, re.IGNORECASE)
        or name.casefold() == ".exe"
    ):
        raise ValueError("Enter only the executable filename, e.g. Game.exe.")
    return name.casefold()


def configured_games(names: Iterable[str]) -> frozenset[str]:
    """Reject invalid and ambiguous configuration rather than guessing games."""
    return frozenset(normalize_executable(name) for name in names)


def running_games(names: Iterable[str], *, process_iter=None) -> frozenset[str]:
    """Read real process names through psutil; ignore inaccessible processes."""
    requested = configured_games(names)
    if not requested:
        return frozenset()
    iterator = process_iter if process_iter is not None else psutil.process_iter
    matches: set[str] = set()
    try:
        processes = iterator(attrs=["name"], ad_value=None)
        for process in processes:
            try:
                name = process.info.get("name")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
                continue
            if not isinstance(name, str):
                continue
            folded = name.casefold()
            if folded in requested:
                matches.add(folded)
    except (psutil.Error, OSError):
        # Errors in enumeration must not trigger an unsolicited unload.
        return frozenset()
    return frozenset(matches)


@dataclass(frozen=True)
class GameTransition:
    active_games: frozenset[str]
    game_started: bool
    game_finished: bool
    unload_model: str | None


class GameGuard:
    """Pure state machine. The caller owns the polling and any I/O.

    Only a model explicitly recorded after a NEXUS chat response is eligible.
    A transition never triggers a GPU command by itself, and there is no
    automatic model preload on game exit.
    """

    def __init__(self, names: Iterable[str] = ()) -> None:
        self.names = configured_games(names)
        self.active_games: frozenset[str] = frozenset()
        self.last_nexus_model: str | None = None

    def set_games(self, names: Iterable[str]) -> None:
        self.names = configured_games(names)
        # Preserve currently observed game state until the next observation.

    def remember_nexus_model(self, model: str) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("The model name must not be empty.")
        self.last_nexus_model = model.strip()

    def observe(
        self, process_names: Iterable[str], *, allow_unload: bool = False
    ) -> GameTransition:
        matches = frozenset(
            name.casefold()
            for name in process_names
            if isinstance(name, str) and name.casefold() in self.names
        )
        was_playing = bool(self.active_games)
        playing = bool(matches)
        started = playing and not was_playing
        finished = was_playing and not playing
        self.active_games = matches
        unload = self.last_nexus_model if started and allow_unload else None
        return GameTransition(matches, started, finished, unload)
