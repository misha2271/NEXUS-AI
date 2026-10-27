"""Storage CIM parsing, actual command boundary, and unsupported-provider behavior."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus_ai.storage import (
    MAX_JSON_BYTES,
    STORAGE_SCRIPT,
    StorageDiagnostics,
    parse_storage_payload,
    run_windows_json,
)


def disk(**changes):
    data = {
        "device_id": "0",
        "name": "Actual provider name",
        "media_type": "SSD",
        "bus_type": "NVMe",
        "health_status": "Healthy",
        "operational_status": ["OK"],
        "size_bytes": 512_000_000_000,
        "counters_available": True,
        "temperature_c": 39,
        "wear_percent": 12,
        "power_on_hours": 750,
        "read_errors_total": 0,
        "write_errors_total": 1,
        "counter_error": None,
    }
    data.update(changes)
    return data


def payload(*disks):
    return {"schema_version": 1, "disks": list(disks)}


def test_supported_cim_fields_are_preserved_without_inventing_health_percentage():
    report = parse_storage_payload(payload(disk()))
    reading = report.disks[0]
    assert report.available and reading.name == "Actual provider name"
    assert reading.temperature_c == 39 and reading.wear_percent == 12
    assert reading.power_on_hours == 750 and reading.write_errors_total == 1
    assert reading.health_status == "Healthy"
    assert not hasattr(reading, "health_percent")
    assert not hasattr(reading, "remaining_life_percent")
    assert not hasattr(reading, "free_space_bytes")


def test_absent_counters_and_provider_zero_temperature_never_become_fake_values():
    report = parse_storage_payload(
        payload(disk(counters_available=False, counter_error="unavailable"))
    )
    reading = report.disks[0]
    assert not reading.counters_available
    assert reading.temperature_c is None and reading.wear_percent is None
    assert reading.power_on_hours is None and reading.read_errors_total is None
    assert "unavailable" in reading.counter_error
    zero = parse_storage_payload(payload(disk(temperature_c=0, wear_percent=0)))
    assert zero.disks[0].temperature_c is None
    assert zero.disks[0].wear_percent == 0  # a raw consumed-wear counter, not 100% health


def test_null_and_over_wear_limit_are_not_reinterpreted_as_remaining_health():
    report = parse_storage_payload(payload(disk(wear_percent=110, temperature_c=None)))
    assert report.disks[0].wear_percent == 110
    assert report.disks[0].temperature_c is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("temperature_c", True),
        ("temperature_c", float("nan")),
        ("temperature_c", -1),
        ("temperature_c", 256),
        ("wear_percent", -1),
        ("wear_percent", 256),
        ("power_on_hours", 65536),
        ("read_errors_total", -1),
        ("write_errors_total", "0"),
        ("size_bytes", True),
        ("size_bytes", 2**64),
        ("device_id", ""),
        ("name", "name\nforged status"),
        ("counters_available", 1),
        ("operational_status", "OK"),
        ("counter_error", "raw diagnostic with secrets"),
    ],
)
def test_invalid_native_field_is_rejected(field, value):
    with pytest.raises(ValueError):
        parse_storage_payload(payload(disk(**{field: value})))


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        {"schema_version": True, "disks": []},
        {"schema_version": 2, "disks": []},
        {"schema_version": 1, "disks": {}},
        {"schema_version": 1, "disks": [None]},
    ],
)
def test_invalid_payload_is_rejected(value):
    with pytest.raises(ValueError):
        parse_storage_payload(value)


def test_duplicate_id_rejected_and_empty_inventory_is_not_synthesized():
    with pytest.raises(ValueError, match="duplicate"):
        parse_storage_payload(payload(disk(), disk()))
    report = parse_storage_payload(payload())
    assert report.available and report.disks == ()


def test_linux_does_not_attempt_powershell_or_report_host_filesystem_as_ssd_health():
    def forbidden(_):
        pytest.fail("must not invoke Windows commands on another platform")

    report = StorageDiagnostics(platform="linux", query=forbidden).collect()
    assert not report.available and report.disks == ()


def test_service_passes_only_constant_read_only_script_to_injected_query():
    calls = []

    def query(script):
        calls.append(script)
        return payload(disk(name="Name with $(untrusted-expression)"))

    report = StorageDiagnostics(platform="win32", query=query).collect()
    assert calls == [STORAGE_SCRIPT]
    assert "$(untrusted-expression)" in report.disks[0].name
    assert "Get-PhysicalDisk" in STORAGE_SCRIPT
    assert "Get-StorageReliabilityCounter" in STORAGE_SCRIPT
    for forbidden in ("Set-PhysicalDisk", "Invoke-Expression", "Start-Process", "-Verb RunAs"):
        assert forbidden not in STORAGE_SCRIPT


@pytest.mark.parametrize(
    "error",
    [
        PermissionError("access denied"),
        ValueError("invalid JSON"),
        subprocess.TimeoutExpired("fixed script", 20),
        RuntimeError("provider missing"),
    ],
)
def test_service_reports_unavailable_without_elevation_or_partial_fabrication(error):
    def query(_):
        raise error

    report = StorageDiagnostics(platform="win32", query=query).collect()
    assert not report.available and not report.disks
    assert "no elevation" in report.message


def test_powershell_runner_uses_fixed_argument_list_utf8_timeout_and_no_shell():
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="\ufeff" + json.dumps(payload(disk())))

    program = Path("/verified-system/WindowsPowerShell/v1.0/powershell.exe")
    result = run_windows_json(STORAGE_SCRIPT, runner=runner, executable=program)
    assert result["disks"][0]["device_id"] == "0"
    command, options = calls[0]
    assert command == [
        str(program),
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        STORAGE_SCRIPT,
    ]
    assert options["shell"] is False and options["timeout"] == 20
    assert options["encoding"] == "utf-8" and options["errors"] == "strict"
    assert options["capture_output"] is True and options["check"] is False


def test_failure_does_not_copy_raw_powershell_stderr_into_user_message():
    def runner(*_, **__):
        return SimpleNamespace(returncode=5, stdout="", stderr="secret device serial must not leak")

    with pytest.raises(RuntimeError) as caught:
        run_windows_json(STORAGE_SCRIPT, runner=runner, executable=Path("fixed.exe"))
    assert "5" in str(caught.value)
    assert "secret" not in str(caught.value)


def test_oversized_or_truncated_json_never_looks_like_a_successful_scan():
    for output in ("x" * (MAX_JSON_BYTES + 1), "{truncated"):
        with pytest.raises(ValueError):
            run_windows_json(
                STORAGE_SCRIPT,
                runner=lambda *_, value=output, **__: SimpleNamespace(returncode=0, stdout=value),
                executable=Path("fixed.exe"),
            )


def test_payload_parsing_does_not_mutate_provider_records():
    original = payload(disk())
    before = copy.deepcopy(original)
    parse_storage_payload(original)
    assert original == before
