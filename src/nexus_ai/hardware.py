"""Read-only Windows PnP/baseboard evidence; vendor-name matches are not SDK support.

No vendor DLL is loaded, downloaded, or executed. No HID packet, RGB write, fan
command, rumble, or firmware operation exists here. Candidate identification is
strictly separated from compatibility and physical validation.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import Callable

from nexus_ai.i18n import Text
from nexus_ai.storage import _text, run_windows_json

HARDWARE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$boards = @(
    Get-CimInstance -ClassName Win32_BaseBoard -ErrorAction Stop | ForEach-Object {
        [pscustomobject]@{ manufacturer = [string]$_.Manufacturer; product = [string]$_.Product }
    }
)
$devices = @(
    Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction Stop | ForEach-Object {
        [pscustomobject]@{
            name = [string]$_.Name
            manufacturer = [string]$_.Manufacturer
            class_name = [string]$_.PNPClass
            status = [string]$_.Status
            hardware_ids = @($_.HardwareID | ForEach-Object { [string]$_ })
        }
    }
)
$fans = @()
$fan_inventory_available = $false
try {
    $fans = @(
        Get-CimInstance -ClassName Win32_Fan -ErrorAction Stop | ForEach-Object {
            [pscustomobject]@{ name = [string]$_.Name; status = [string]$_.Status }
        }
    )
    $fan_inventory_available = $true
} catch { }
[pscustomobject]@{
    schema_version = 1; boards = $boards; devices = $devices;
    fans = $fans; fan_inventory_available = $fan_inventory_available
} | ConvertTo-Json -Depth 6 -Compress
""".strip()


@dataclass(frozen=True)
class BoardReading:
    manufacturer: str
    product: str


@dataclass(frozen=True)
class DeviceReading:
    name: str
    manufacturer: str
    class_name: str
    status: str
    hardware_ids: tuple[str, ...]


@dataclass(frozen=True)
class FanReading:
    name: str
    status: str


@dataclass(frozen=True)
class HardwareCapability:
    key: str
    title: str
    candidate_names: tuple[str, ...]
    reason: str
    compatible: bool | None = None
    validated: bool = False
    writes_supported: bool = False

    @property
    def detected(self) -> bool:
        """Detection means candidate evidence only, never compatible or validated."""
        return bool(self.candidate_names)


@dataclass(frozen=True)
class HardwareReport:
    available: bool
    boards: tuple[BoardReading, ...]
    devices: tuple[DeviceReading, ...]
    fans: tuple[FanReading, ...]
    fan_inventory_available: bool
    capabilities: tuple[HardwareCapability, ...]
    message: str

    @property
    def board(self) -> BoardReading | None:
        return self.boards[0] if self.boards else None


def _capabilities(
    boards: tuple[BoardReading, ...],
    devices: tuple[DeviceReading, ...],
    fans: tuple[FanReading, ...],
) -> tuple[HardwareCapability, ...]:
    msi = tuple(
        f"{board.manufacturer} / {board.product}"
        for board in boards
        if any(
            marker in board.manufacturer.casefold()
            for marker in ("micro-star", "micro star", "msi")
        )
    )
    g560 = tuple(device.name for device in devices if "g560" in device.name.casefold())
    xbox = tuple(device.name for device in devices if "xbox" in device.name.casefold())
    return (
        HardwareCapability(
            "msi_mystic_light",
            "MSI Mystic Light",
            msi,
            Text(
                (
                    "MSI board identity is detection evidence only. Mystic Light "
                    "compatibility and the vendor SDK are not validated; RGB writes "
                    "remain disabled."
                )
            ),
        ),
        HardwareCapability(
            "logitech_g560",
            "Logitech G560",
            g560,
            Text(
                (
                    "A G560 name match does not validate Logitech LED SDK support. "
                    "Speaker RGB, audio and firmware controls remain disabled."
                )
            ),
        ),
        HardwareCapability(
            "xbox_elite_2",
            "Xbox Elite Series 2",
            xbox,
            Text(
                (
                    "Xbox-family PnP names do not prove Elite Series 2 identity or "
                    "paddle support. Standard XInput state can be read separately; Elite "
                    "features, GameInput and rumble remain unvalidated and disabled."
                )
            ),
        ),
        HardwareCapability(
            "cooling",
            Text("Cooling"),
            tuple(fan.name for fan in fans),
            Text(
                (
                    "Win32_Fan inventory does not prove actual RPM, temperature or "
                    "writable control. Cooling controls remain disabled without a "
                    "supported, physically validated provider."
                )
            ),
        ),
    )


def _list(payload: dict, key: str, maximum: int) -> list:
    result = payload.get(key)
    if not isinstance(result, list) or len(result) > maximum:
        raise ValueError(Text("Invalid Windows hardware list: {field}.", field=key))
    return result


def parse_hardware_payload(payload: object) -> HardwareReport:
    if (
        not isinstance(payload, dict)
        or type(payload.get("schema_version")) is not int
        or payload["schema_version"] != 1
    ):
        raise ValueError(Text("Unsupported Windows diagnostic response."))
    boards = []
    for board in _list(payload, "boards", 32):
        if not isinstance(board, dict):
            raise ValueError(Text("Invalid Windows baseboard entry."))
        boards.append(
            BoardReading(
                _text(board.get("manufacturer"), "manufacturer"),
                _text(board.get("product"), "product"),
            )
        )
    devices = []
    for device in _list(payload, "devices", 4096):
        if not isinstance(device, dict):
            raise ValueError(Text("Invalid Windows device entry."))
        identifiers = device.get("hardware_ids")
        if not isinstance(identifiers, list) or len(identifiers) > 32:
            raise ValueError(Text("Invalid Windows device hardware identifiers."))
        devices.append(
            DeviceReading(
                _text(device.get("name"), "name"),
                _text(device.get("manufacturer"), "manufacturer"),
                _text(device.get("class_name"), "class_name"),
                _text(device.get("status"), "status"),
                tuple(_text(value, "hardware_id") for value in identifiers),
            )
        )
    fans = []
    for fan in _list(payload, "fans", 256):
        if not isinstance(fan, dict):
            raise ValueError(Text("Invalid Windows fan entry."))
        fans.append(FanReading(_text(fan.get("name"), "name"), _text(fan.get("status"), "status")))
    fan_inventory = payload.get("fan_inventory_available")
    if type(fan_inventory) is not bool:
        raise ValueError(Text("Invalid Windows fan inventory state."))
    if not fan_inventory and fans:
        raise ValueError(Text("Inconsistent Windows fan inventory state."))
    return HardwareReport(
        True,
        tuple(boards),
        tuple(devices),
        tuple(fans),
        fan_inventory,
        _capabilities(tuple(boards), tuple(devices), tuple(fans)),
        Text(
            (
                "Read-only Windows inventory collected. Candidate matches do not "
                "enable hardware controls."
            )
        ),
    )


class HardwareInventory:
    def __init__(
        self, *, platform: str | None = None, query: Callable[[str], object] = run_windows_json
    ):
        self.platform = sys.platform if platform is None else platform
        self.query = query

    def collect(self) -> HardwareReport:
        if self.platform != "win32":
            return HardwareReport(
                False,
                (),
                (),
                (),
                False,
                _capabilities((), (), ()),
                Text("Windows hardware inventory is unavailable on this platform."),
            )
        try:
            return parse_hardware_payload(self.query(HARDWARE_SCRIPT))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            return HardwareReport(
                False,
                (),
                (),
                (),
                False,
                _capabilities((), (), ()),
                Text(
                    (
                        "Windows hardware query unavailable. No SDK was loaded and no "
                        "device commands were sent."
                    )
                ),
            )
