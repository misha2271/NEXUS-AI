"""Pure game/lifecycle state machine. Network actions belong in worker jobs.

The controller never kills Ollama, deletes model files, or automatically touches
models that NEXUS has not successfully used. Auto unloading requires an explicit
opt-in game configuration and a confirmed game match. Restore is demand driven.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexus_ai.gaming import GameDetection, GameProfile
from nexus_ai.i18n import Text
from nexus_ai.profiles import PROFILE_NAMES


@dataclass(frozen=True)
class LifecycleDecision:
    mode: str
    game_name: str | None
    unload_model: str | None
    status: str


class LifecycleController:
    def __init__(self, base_mode: str = "Smart"):
        self._validate_mode(base_mode)
        self.base_mode = base_mode
        self.active: GameProfile | None = None
        self.busy = False
        self.owned_model: str | None = None
        self._resident = False
        self._in_flight: str | None = None
        self._failed_targets: set[str] = set()
        self._uncertain = False
        self._restore_requested = False

    @staticmethod
    def _validate_mode(mode: str) -> None:
        if mode not in PROFILE_NAMES:
            raise ValueError(Text("Choose a supported performance profile."))

    @property
    def mode(self) -> str:
        return self.active.mode if self.active is not None else self.base_mode

    @property
    def pending_operation(self) -> str | None:
        return self._in_flight

    def set_base_mode(self, mode: str) -> LifecycleDecision:
        self._validate_mode(mode)
        self.base_mode = mode
        return self._decision()

    def note_model_used(self, model: str) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError(Text("Select an installed model before sending a message."))
        self.owned_model = model
        self._resident = True
        self._failed_targets.discard(model)

    def set_busy(self, busy: bool) -> LifecycleDecision:
        if type(busy) is not bool:
            raise ValueError("busy must be a boolean")
        self.busy = busy
        return self._decision()

    def observe(self, detection: GameDetection) -> LifecycleDecision:
        self._uncertain = not detection.complete
        if detection.active is not None or detection.complete or detection.confirmed_exit:
            if detection.active != self.active:
                self._failed_targets.clear()
                self._restore_requested = False
            self.active = detection.active
        return self._decision()

    def unloaded(self, model: str) -> None:
        """Call only after the server acknowledges a completed unload operation."""
        if self.owned_model == model:
            self._resident = False
            self._restore_requested = False
        if self._in_flight == model:
            self._in_flight = None

    def unload_failed(self, model: str) -> None:
        if self._in_flight == model:
            self._in_flight = None
            self._failed_targets.add(model)

    def request_restore(self) -> str:
        """The next explicit chat/load request may load the selected model normally.

        This intentionally performs no network operation. Active games keep their
        configured inference policy; ending a game restores the user's base mode.
        """
        self._restore_requested = True
        return self.mode

    def _decision(self) -> LifecycleDecision:
        target = None
        if (
            self.active is not None
            and self.active.unload_model
            and self._resident
            and self.owned_model
            and not self.busy
            and self._in_flight is None
            and self.owned_model not in self._failed_targets
            and not self._restore_requested
        ):
            target = self.owned_model
            self._in_flight = target
        if self._uncertain and self.active is not None:
            status = Text("Game detection is incomplete; keeping the current game mode.")
        elif self.active is not None:
            status = Text(
                "Game mode: {game}. Models restore only when requested.", game=self.active.name
            )
        else:
            status = Text("Using the selected mode. Models restore only when requested.")
        if self.active is not None and self._restore_requested:
            status = Text(
                "Model restoration was requested; automatic unloading is paused for this game."
            )
        if self.active is not None and self.busy and self._resident and not self._restore_requested:
            status = Text("Model unloading is deferred until the active request finishes.")
        if self.owned_model in self._failed_targets:
            status = Text(
                "Model unloading failed; automatic retry is paused until a new request "
                "or game transition."
            )
        return LifecycleDecision(
            self.mode, self.active.name if self.active else None, target, status
        )
