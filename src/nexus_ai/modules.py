"""Device-module contracts, without unvalidated hardware operations.

Future providers must probe on a worker thread, report actual capabilities, and
undergo hardware validation before any write controls can be wired to the UI.
No SDK, device command, firmware installer, or elevated process is invoked here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class IntegrationStatus:
    available: bool
    validated: bool
    reason: str
    capabilities: frozenset[str] = frozenset()

    def permits(self, capability: str) -> bool:
        return self.available and self.validated and capability in self.capabilities


class IntegrationProvider(Protocol):
    """Contract only; implementations must perform probing outside the UI thread."""

    def probe(self) -> IntegrationStatus: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class ModuleSpec:
    key: str
    title: str
    description: str
    requirements: str
    controls: tuple[str, ...]


MODULES = (
    ModuleSpec(
        "gaming",
        "Gaming",
        "A quieter inference budget while you play.",
        "Opt-in exact executable detection switches inference profiles and restores the previous "
        "profile on game exit. Only NEXUS-used models may be unloaded with consent. "
        "FPS capture, OS tuning, and fan control remain unavailable.",
        ("Fan control",),
    ),
    ModuleSpec(
        "rgb",
        "RGB Studio",
        "A future home for supported lighting devices.",
        "Read-only Windows hardware inventory can identify candidates, not SDK support. "
        "No RGB SDK is validated; no HID packets or lighting commands are sent.",
        ("Apply lighting",),
    ),
    ModuleSpec(
        "g560",
        "Logitech G560",
        "Speaker lighting and device capabilities.",
        "Requires a supported Logitech SDK, a connected G560, and physical-device validation. "
        "No speaker, lighting, audio, or firmware integration is implemented.",
        ("Apply speaker RGB",),
    ),
    ModuleSpec(
        "gamepad",
        "Gamepad Lab",
        "Read-only diagnostics for standard XInput controller slots.",
        "Windows XInput reports connected slots, buttons, triggers, and stick axes "
        "when available. Elite-specific paddles, rumble, calibration, and firmware writes "
        "remain unavailable. A slot does not identify an Elite model.",
        ("Test rumble",),
    ),
    ModuleSpec(
        "ssd",
        "SSD Health",
        "Health information from supported storage providers.",
        "Read-only Windows Storage reliability counters report only fields exposed by the "
        "drive and driver. Missing counters remain unavailable; wear is consumed wear, "
        "not a computed health score. No drive writes are performed.",
        ("Write drive firmware",),
    ),
    ModuleSpec(
        "updates",
        "Update Center",
        "Check GitHub Releases and verify explicitly approved downloads.",
        "Checks use the official repository. Downloads require explicit approval and a GitHub "
        "SHA-256 asset digest; major updates need separate approval. Hash verification is "
        "not publisher signing. Installation remains unavailable.",
        ("Install update",),
    ),
)


class IntegrationRegistry:
    """Default-deny capability registry; no placeholder is registered as supported."""

    def __init__(self) -> None:
        self._statuses: dict[str, IntegrationStatus] = {}

    def status(self, key: str) -> IntegrationStatus:
        return self._statuses.get(
            key, IntegrationStatus(False, False, "No validated hardware provider connected")
        )

    def record_probe(self, key: str, status: IntegrationStatus) -> None:
        """Accept a completed background probe, never run an SDK on the UI thread."""
        self._statuses[key] = status
