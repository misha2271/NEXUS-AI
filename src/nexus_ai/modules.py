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
        "The existing Gaming profile changes Ollama request options only. Game detection, "
        "FPS capture, OS tuning, and fan control are not implemented.",
        ("Fan control",),
    ),
    ModuleSpec(
        "rgb",
        "RGB Studio",
        "A future home for supported lighting devices.",
        "No RGB SDK is connected or validated. Device discovery and lighting writes are "
        "unavailable; no HID packets or device commands are sent.",
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
        "A future workspace for controller diagnostics.",
        "No controller backend is connected. Input capture, rumble, calibration, and "
        "firmware operations require a validated provider.",
        ("Test rumble",),
    ),
    ModuleSpec(
        "ssd",
        "SSD Health",
        "Health information from supported storage providers.",
        "No SMART/NVMe health provider is connected. Health, endurance, and drive temperature "
        "are unavailable. Filesystem free space is not a drive health measurement.",
        ("Read SMART",),
    ),
    ModuleSpec(
        "updates",
        "Update Center",
        "Installed version and future update verification.",
        "Automatic update checks and installers are not implemented. A future provider must "
        "verify signed metadata and artifacts before offering an update. Nothing is downloaded "
        "or installed automatically.",
        ("Check for updates", "Install update"),
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
