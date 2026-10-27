"""PnP candidate evidence is not device support or permission to issue writes."""

from __future__ import annotations

import subprocess

import pytest

from nexus_ai.hardware import HARDWARE_SCRIPT, HardwareInventory, parse_hardware_payload


def device(name="Logitech G560 Gaming Speaker", **changes):
    result = {
        "name": name,
        "manufacturer": "Logitech",
        "class_name": "MEDIA",
        "status": "OK",
        "hardware_ids": ["USB\\VID_046D&PID_EXAMPLE"],
    }
    result.update(changes)
    return result


def payload(**changes):
    result = {
        "schema_version": 1,
        "boards": [
            {"manufacturer": "Micro-Star International Co., Ltd.", "product": "Provider board name"}
        ],
        "devices": [device(), device("Xbox Controller", manufacturer="Microsoft")],
        "fans": [{"name": "Provider fan name", "status": "OK"}],
        "fan_inventory_available": True,
    }
    result.update(changes)
    return result


def test_real_inventory_records_survive_without_enabling_or_claiming_sdk_support():
    report = parse_hardware_payload(payload())
    assert report.available
    assert report.board.manufacturer == "Micro-Star International Co., Ltd."
    assert report.devices[0].hardware_ids == ("USB\\VID_046D&PID_EXAMPLE",)
    assert report.fans[0].name == "Provider fan name"
    assert all(capability.detected for capability in report.capabilities)
    for capability in report.capabilities:
        assert capability.compatible is None
        assert not capability.validated and not capability.writes_supported
    elite = next(c for c in report.capabilities if c.key == "xbox_elite_2")
    assert "do not prove Elite Series 2 identity" in elite.reason


def test_unknown_names_and_missing_fan_provider_do_not_synthesize_devices():
    report = parse_hardware_payload(
        payload(
            boards=[], devices=[device("USB Audio Device")], fans=[], fan_inventory_available=False
        )
    )
    assert not any(capability.detected for capability in report.capabilities)
    assert report.board is None
    assert report.fans == () and not report.fan_inventory_available


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"schema_version": True},
        {"boards": None},
        {"devices": {}},
        {"fans": [None]},
        {"fan_inventory_available": False},
        {"devices": [device(hardware_ids="a string is not a list")]},
        {"devices": [device(name="spoof\nconnected")]},
        {"devices": [device(status=1)]},
        {"boards": [{"manufacturer": "known", "product": None}]},
    ],
)
def test_invalid_provider_data_is_rejected(changes):
    with pytest.raises(ValueError):
        parse_hardware_payload(payload(**changes))


def test_unsupported_platform_never_loads_vendor_sdk_or_invokes_query():
    def forbidden(_):
        pytest.fail("must not query Windows hardware on another platform")

    report = HardwareInventory(platform="linux", query=forbidden).collect()
    assert not report.available and not report.devices
    assert all(not c.validated and not c.writes_supported for c in report.capabilities)


def test_collection_passes_constant_script_with_no_serial_number_capture_or_writes():
    calls = []

    def query(script):
        calls.append(script)
        return payload()

    assert HardwareInventory(platform="win32", query=query).collect().available
    assert calls == [HARDWARE_SCRIPT]
    assert "Get-CimInstance" in HARDWARE_SCRIPT
    for forbidden in (
        "SerialNumber",
        "PNPDeviceID",
        "Invoke-CimMethod",
        "Set-CimInstance",
        "Add-Type",
        "LoadLibrary",
        "Invoke-Expression",
        "-Verb RunAs",
    ):
        assert forbidden not in HARDWARE_SCRIPT


@pytest.mark.parametrize(
    "error",
    [
        PermissionError("denied"),
        ValueError("bad schema"),
        subprocess.TimeoutExpired("fixed script", 20),
    ],
)
def test_access_and_timeout_failures_leave_capabilities_disabled(error):
    def query(_):
        raise error

    report = HardwareInventory(platform="win32", query=query).collect()
    assert not report.available and not report.devices
    assert all(not capability.writes_supported for capability in report.capabilities)
