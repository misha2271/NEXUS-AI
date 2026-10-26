"""Exercise packaging diagnostics without pretending a Windows binary was built."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

import nexus_ai.diagnostics as diagnostics
from nexus_ai.app import main
from nexus_ai.settings import Settings, SettingsStore
from nexus_ai.telemetry import TelemetryCollector, TelemetrySnapshot


@pytest.fixture
def isolated_preferences(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return SettingsStore()


@pytest.fixture
def healthy_collector(monkeypatch):
    instances = []

    class Collector:
        def __init__(self):
            self.samples = 0
            self.closed = False
            instances.append(self)

        def sample(self):
            self.samples += 1
            return TelemetrySnapshot(
                cpu_percent=25.0,
                ram_percent=50.0,
                ram_used_bytes=4 * 1024**3,
                ram_total_bytes=8 * 1024**3,
                ram_available_bytes=4 * 1024**3,
                gpus=(),
                gpu_status="NVIDIA telemetry unavailable: no driver in test fixture",
            )

        def close(self):
            self.closed = True

    monkeypatch.setattr(diagnostics, "TelemetryCollector", Collector)
    return instances


def test_probe_survives_relaunch_and_preserves_actual_preferences(
    qapp, isolated_preferences, healthy_collector, tmp_path
):
    actual = Settings(model="personal-model", profile="Gaming")
    isolated_preferences.save(actual)
    original_bytes = isolated_preferences.path.read_bytes()
    first_path = tmp_path / "reports" / "first.json"
    second_path = tmp_path / "reports" / "second.json"
    assert diagnostics.run_self_test(qapp, first_path) == 0
    assert diagnostics.run_self_test(qapp, second_path) == 0

    first = json.loads(first_path.read_text(encoding="utf-8"))
    second = json.loads(second_path.read_text(encoding="utf-8"))
    for report in (first, second):
        assert report["status"] == "passed"
        assert report["errors"] == []
        assert report["ui_constructed"] is True
        assert report["settings_roundtrip"] is True
        assert report["settings_path"] == str(isolated_preferences.path)
        assert report["persistence_probe_path"] == str(
            isolated_preferences.path.with_name(".packaging-self-test.json")
        )
        assert isinstance(report["frozen"], bool)
        assert report["qt_platform"] == qapp.platformName()
        assert isinstance(report["nvml_binding_available"], bool)
        assert report["telemetry"]["ram_total_bytes"] == 8 * 1024**3
    assert first["previous_settings"] == asdict(Settings())
    assert second["previous_settings"] == asdict(Settings(profile="Eco"))
    assert isolated_preferences.path.read_bytes() == original_bytes
    assert isolated_preferences.load() == actual
    assert len(healthy_collector) == 2
    assert all(instance.samples == 2 and instance.closed for instance in healthy_collector)


def test_probe_reports_settings_write_failure(
    monkeypatch, qapp, isolated_preferences, healthy_collector, tmp_path
):
    def denied_save(self, settings):
        raise PermissionError("settings directory is not writable")

    monkeypatch.setattr(SettingsStore, "save", denied_save)
    report_path = tmp_path / "failure.json"
    assert diagnostics.run_self_test(qapp, report_path) == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["errors"] == ["settings directory is not writable"]
    assert report["settings_roundtrip"] is False
    assert report["ui_constructed"] is False
    assert healthy_collector == []


def test_probe_detects_settings_that_cannot_be_restored(
    monkeypatch, qapp, isolated_preferences, healthy_collector, tmp_path
):
    original_load = SettingsStore.load

    def inconsistent_load(self):
        loaded = original_load(self)
        if self.path.name == ".packaging-self-test.json" and self.path.exists():
            return Settings(profile="Smart")
        return loaded

    monkeypatch.setattr(SettingsStore, "load", inconsistent_load)
    report_path = tmp_path / "restore-failure.json"
    assert diagnostics.run_self_test(qapp, report_path) == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["settings_roundtrip"] is False
    assert "could not be restored" in report["errors"][0]
    assert healthy_collector == []


def test_missing_nvidia_driver_is_a_successful_packaging_probe(
    monkeypatch, qapp, isolated_preferences, tmp_path
):
    memory = SimpleNamespace(percent=50.0, used=4096, total=8192, available=4096)
    psutil_fixture = SimpleNamespace(
        cpu_percent=lambda interval: 12.0, virtual_memory=lambda: memory
    )

    class MissingDriver:
        def nvmlInit(self):
            raise RuntimeError("driver absent for test")

    collector = TelemetryCollector(psutil_module=psutil_fixture, nvml_module=MissingDriver())
    monkeypatch.setattr(diagnostics, "TelemetryCollector", lambda: collector)
    report_path = tmp_path / "no-driver.json"
    assert diagnostics.run_self_test(qapp, report_path) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["telemetry"]["gpus"] == []
    assert "driver absent for test" in report["telemetry"]["gpu_status"]
    assert report["telemetry"]["ram_total_bytes"] == 8192
    with pytest.raises(RuntimeError, match="closed"):
        collector.sample()


def test_telemetry_failure_is_reported_and_collector_is_closed(
    monkeypatch, qapp, isolated_preferences, tmp_path
):
    closed = []

    class BrokenCollector:
        def sample(self):
            raise RuntimeError("psutil extension could not initialize")

        def close(self):
            closed.append(True)

    monkeypatch.setattr(diagnostics, "TelemetryCollector", BrokenCollector)
    report_path = tmp_path / "telemetry-failure.json"
    assert diagnostics.run_self_test(qapp, report_path) == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["errors"] == ["psutil extension could not initialize"]
    assert closed == [True]


def test_unwritable_report_returns_nonzero(qapp, isolated_preferences, healthy_collector, tmp_path):
    not_directory = tmp_path / "not-a-directory"
    not_directory.write_text("occupied", encoding="utf-8")
    assert diagnostics.run_self_test(qapp, not_directory / "report.json") == 1
    assert healthy_collector[0].closed


@pytest.mark.parametrize(
    "binding_state,expected_exit,expected_available",
    [("absent", 0, False), ("working", 0, True), ("broken", 1, False)],
)
def test_optional_nvml_binding_must_actually_import_when_present(
    binding_state,
    expected_exit,
    expected_available,
    monkeypatch,
    qapp,
    isolated_preferences,
    healthy_collector,
    tmp_path,
):
    imports = []

    def find_spec(name):
        assert name == "pynvml"
        return None if binding_state == "absent" else object()

    def import_module(name):
        imports.append(name)
        if binding_state == "broken":
            raise ImportError("pynvml dependency could not be imported")
        return SimpleNamespace()

    monkeypatch.setattr(
        diagnostics,
        "importlib",
        SimpleNamespace(util=SimpleNamespace(find_spec=find_spec), import_module=import_module),
    )
    report_path = tmp_path / "binding-report.json"
    assert diagnostics.run_self_test(qapp, report_path) == expected_exit
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["nvml_binding_available"] is expected_available
    assert imports == ([] if binding_state == "absent" else ["pynvml"])
    if binding_state == "broken":
        assert report["status"] == "failed"
        assert report["errors"] == ["pynvml dependency could not be imported"]
        assert healthy_collector == []
    else:
        assert report["status"] == "passed"
        assert report["errors"] == []
        assert healthy_collector[0].closed


@pytest.mark.parametrize(
    "invalid_fields,message",
    [
        ({"cpu_percent": None}, "CPU utilization"),
        ({"cpu_percent": float("nan")}, "CPU utilization"),
        ({"cpu_percent": -1.0}, "CPU utilization"),
        ({"cpu_percent": 101.0}, "CPU utilization"),
        ({"ram_total_bytes": 0}, "physical memory"),
        ({"ram_percent": None}, "invalid memory telemetry"),
        ({"ram_percent": float("nan")}, "invalid memory telemetry"),
        ({"ram_used_bytes": 9 * 1024**3}, "invalid memory telemetry"),
        ({"ram_available_bytes": None}, "invalid memory telemetry"),
    ],
)
def test_suppressed_cpu_or_memory_read_failures_do_not_pass_packaging_probe(
    invalid_fields,
    message,
    monkeypatch,
    qapp,
    isolated_preferences,
    healthy_collector,
    tmp_path,
):
    base_collector = diagnostics.TelemetryCollector

    class InvalidCollector(base_collector):
        def sample(self):
            return replace(super().sample(), **invalid_fields)

    monkeypatch.setattr(diagnostics, "TelemetryCollector", InvalidCollector)
    report_path = tmp_path / "invalid-telemetry.json"
    assert diagnostics.run_self_test(qapp, report_path) == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert message in report["errors"][0]
    assert healthy_collector[0].samples == 2
    assert healthy_collector[0].closed


@pytest.mark.parametrize("arguments", [["--self-test"], ["--self-test-report", "report.json"]])
def test_self_test_cli_requires_both_flags(arguments, capsys):
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2
    assert "Use --self-test and --self-test-report PATH together" in capsys.readouterr().err
