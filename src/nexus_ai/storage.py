"""Read-only Windows Storage CIM diagnostics; no elevation, disk writes, or scoring.

Get-StorageReliabilityCounter is a supported Windows provider, not a universal
raw-SMART parser. Missing counters stay None. Wear is consumed endurance, never a
made-up remaining-health score. The caller must run collection off the UI thread.
"""

from __future__ import annotations

import ctypes
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from nexus_ai.i18n import Text

MAX_JSON_BYTES = 1_048_576
MAX_DISKS = 256

STORAGE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$records = @(
    Get-PhysicalDisk -ErrorAction Stop | ForEach-Object {
        $disk = $_
        $counter = $null
        $counterError = $null
        try { $counter = $disk | Get-StorageReliabilityCounter -ErrorAction Stop }
        catch { $counterError = 'unavailable' }
        [pscustomobject]@{
            device_id = [string]$disk.DeviceId
            name = [string]$disk.FriendlyName
            media_type = [string]$disk.MediaType
            bus_type = [string]$disk.BusType
            health_status = [string]$disk.HealthStatus
            operational_status = @($disk.OperationalStatus | ForEach-Object { [string]$_ })
            size_bytes = $disk.Size
            counters_available = ($null -ne $counter)
            temperature_c = $counter.Temperature
            wear_percent = $counter.Wear
            power_on_hours = $counter.PowerOnHours
            read_errors_total = $counter.ReadErrorsTotal
            write_errors_total = $counter.WriteErrorsTotal
            counter_error = $counterError
        }
    }
)
[pscustomobject]@{ schema_version = 1; disks = $records } | ConvertTo-Json -Depth 6 -Compress
""".strip()


@dataclass(frozen=True)
class DiskReading:
    device_id: str
    name: str
    media_type: str
    bus_type: str
    health_status: str
    operational_status: tuple[str, ...]
    size_bytes: int | None
    counters_available: bool
    temperature_c: float | None
    wear_percent: int | None
    power_on_hours: int | None
    read_errors_total: int | None
    write_errors_total: int | None
    counter_error: str | None = None


@dataclass(frozen=True)
class StorageReport:
    available: bool
    disks: tuple[DiskReading, ...]
    message: str


def _powershell_path() -> Path:
    """Resolve the OS system directory rather than searching PATH or the checkout."""
    if sys.platform != "win32":
        raise OSError("Windows PowerShell requires native Windows")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = kernel32.GetSystemDirectoryW
    function.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
    function.restype = ctypes.c_uint
    buffer = ctypes.create_unicode_buffer(32768)
    size = function(buffer, len(buffer))
    if not size or size >= len(buffer):
        raise OSError("Windows system directory could not be resolved")
    executable = Path(buffer.value) / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not executable.is_file():
        raise OSError("Windows PowerShell is unavailable")
    return executable


def run_windows_json(
    script: str,
    *,
    runner: Callable = subprocess.run,
    executable: Path | None = None,
    timeout: float = 20,
) -> object:
    """Execute a constant read-only script. Exposed hooks are for local tests only."""
    program = _powershell_path() if executable is None else executable
    result = runner(
        [str(program), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=timeout,
        check=False,
        shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        # Raw stderr may contain identifying data; do not copy it into logs or UI.
        raise RuntimeError(
            Text("The read-only Windows query failed (exit {code}).", code=result.returncode)
        )
    if len(result.stdout.encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError(Text("The Windows diagnostic response exceeded the size limit."))
    return json.loads(result.stdout.lstrip("\ufeff"))


def _text(value: object, field: str, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError(Text("Invalid Windows diagnostic field: {field}.", field=field))
    return value


def _optional_int(value: object, field: str, maximum: int = 2**64 - 1) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(Text("Invalid Windows diagnostic field: {field}.", field=field))
    return value


def parse_storage_payload(payload: object) -> StorageReport:
    if (
        not isinstance(payload, dict)
        or type(payload.get("schema_version")) is not int
        or payload["schema_version"] != 1
    ):
        raise ValueError(Text("Unsupported Windows diagnostic response."))
    disks = payload.get("disks")
    if not isinstance(disks, list) or len(disks) > MAX_DISKS:
        raise ValueError(Text("Invalid Windows disk list."))
    readings = []
    identities = set()
    for disk in disks:
        if not isinstance(disk, dict):
            raise ValueError(Text("Invalid Windows disk entry."))
        identity = _text(disk.get("device_id"), "device_id", maximum=256)
        if not identity or identity in identities:
            raise ValueError(Text("Invalid or duplicate Windows disk identifier."))
        identities.add(identity)
        available = disk.get("counters_available")
        if type(available) is not bool:
            raise ValueError(
                Text("Invalid Windows diagnostic field: {field}.", field="counters_available")
            )
        operations = disk.get("operational_status")
        if not isinstance(operations, list) or len(operations) > 16:
            raise ValueError(Text("Invalid Windows disk operational status."))
        error = disk.get("counter_error")
        if error is not None:
            error = _text(error, "counter_error", maximum=64)
            if error != "unavailable":
                raise ValueError(Text("Invalid Windows counter error code."))
            error = Text("Reliability counters unavailable for this disk.")
        temperature = disk.get("temperature_c") if available else None
        if temperature is not None:
            if (
                type(temperature) not in (int, float)
                or not math.isfinite(temperature)
                or not 0 <= temperature <= 255
            ):
                raise ValueError(
                    Text("Invalid Windows diagnostic field: {field}.", field="temperature_c")
                )
            # Zero is commonly a provider default and is not validated as a physical reading.
            temperature = float(temperature) if temperature > 0 else None
        readings.append(
            DiskReading(
                device_id=identity,
                name=_text(disk.get("name"), "name"),
                media_type=_text(disk.get("media_type"), "media_type"),
                bus_type=_text(disk.get("bus_type"), "bus_type"),
                health_status=_text(disk.get("health_status"), "health_status"),
                operational_status=tuple(_text(s, "operational_status") for s in operations),
                size_bytes=_optional_int(disk.get("size_bytes"), "size_bytes"),
                counters_available=available,
                temperature_c=temperature,
                wear_percent=_optional_int(disk.get("wear_percent"), "wear_percent", 255)
                if available
                else None,
                power_on_hours=_optional_int(disk.get("power_on_hours"), "power_on_hours", 65535)
                if available
                else None,
                read_errors_total=_optional_int(disk.get("read_errors_total"), "read_errors_total")
                if available
                else None,
                write_errors_total=_optional_int(
                    disk.get("write_errors_total"), "write_errors_total"
                )
                if available
                else None,
                counter_error=error,
            )
        )
    message = Text(
        (
            "Windows storage provider returned {count} disk(s). Counters may "
            "be unavailable or driver defaults."
        ),
        count=len(readings),
    )
    return StorageReport(True, tuple(readings), message)


class StorageDiagnostics:
    """Synchronous read-only collection. Use a worker; no automatic polling or elevation."""

    def __init__(
        self, *, platform: str | None = None, query: Callable[[str], object] = run_windows_json
    ):
        self.platform = sys.platform if platform is None else platform
        self.query = query

    def collect(self) -> StorageReport:
        if self.platform != "win32":
            return StorageReport(
                False, (), Text("Windows Storage diagnostics are unavailable on this platform.")
            )
        try:
            return parse_storage_payload(self.query(STORAGE_SCRIPT))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            return StorageReport(
                False,
                (),
                Text(
                    (
                        "Windows storage query unavailable. Check provider support and "
                        "permissions; no elevation was attempted."
                    )
                ),
            )
