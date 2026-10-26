from types import SimpleNamespace

import pytest

from nexus_ai.telemetry import TelemetryCollector


class FakePsutil:
    def __init__(self):
        self.cpu_calls = 0

    def cpu_percent(self, *, interval):
        assert interval is None
        self.cpu_calls += 1
        return 0 if self.cpu_calls == 1 else 37.5

    def virtual_memory(self):
        return SimpleNamespace(percent=25, used=4_000, total=16_000, available=12_000)


class FakeNVML:
    NVML_TEMPERATURE_GPU = 0

    def __init__(self):
        self.init_calls = 0
        self.shutdown_calls = 0
        self.count = 2

    def nvmlInit(self):
        self.init_calls += 1

    def nvmlShutdown(self):
        self.shutdown_calls += 1

    def nvmlDeviceGetCount(self):
        return self.count

    def nvmlDeviceGetHandleByIndex(self, index):
        return index

    def nvmlDeviceGetName(self, handle):
        return f"NVIDIA test device {handle}".encode()

    def nvmlDeviceGetUtilizationRates(self, handle):
        return SimpleNamespace(gpu=40 + handle)

    def nvmlDeviceGetMemoryInfo(self, handle):
        return SimpleNamespace(used=2_000 + handle, total=8_000)

    def nvmlDeviceGetTemperature(self, handle, sensor):
        assert sensor == self.NVML_TEMPERATURE_GPU
        return 55 + handle


def test_nonblocking_cpu_priming_and_real_ram_values():
    psutil = FakePsutil()
    collector = TelemetryCollector(psutil_module=psutil, nvml_module=None)
    first = collector.sample()
    second = collector.sample()
    assert first.cpu_percent is None
    assert first.cpu_status == "Collecting first CPU sample"
    assert second.cpu_percent == 37.5
    assert second.ram_percent == 25
    assert second.ram_used_bytes == 4_000
    assert second.ram_total_bytes == 16_000
    assert second.ram_available_bytes == 12_000


def test_missing_optional_nvml_package_does_not_break_cpu_or_ram(monkeypatch):
    def missing(name):
        assert name == "pynvml"
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("nexus_ai.telemetry.importlib.import_module", missing)
    collector = TelemetryCollector(psutil_module=FakePsutil())
    collector.sample()
    sample = collector.sample()
    assert sample.gpus == ()
    assert "not installed" in sample.gpu_status
    assert sample.cpu_percent == 37.5
    assert sample.ram_percent == 25


def test_missing_driver_initializes_once_and_does_not_shutdown():
    nvml = FakeNVML()

    def fail():
        nvml.init_calls += 1
        raise RuntimeError("Driver Not Loaded")

    nvml.nvmlInit = fail
    collector = TelemetryCollector(psutil_module=FakePsutil(), nvml_module=nvml)
    assert "Driver Not Loaded" in collector.sample().gpu_status
    assert collector.sample().gpus == ()
    collector.close()
    assert nvml.init_calls == 1
    assert nvml.shutdown_calls == 0


def test_all_devices_and_shutdown_once():
    nvml = FakeNVML()
    collector = TelemetryCollector(psutil_module=FakePsutil(), nvml_module=nvml)
    assert nvml.init_calls == 0  # Initialization is deferred to worker sampling.
    sample = collector.sample()
    assert len(sample.gpus) == 2
    assert sample.gpus[1].name == "NVIDIA test device 1"
    assert sample.gpus[1].utilization_percent == 41
    assert sample.gpus[1].memory_used_bytes == 2_001
    assert sample.gpus[1].memory_total_bytes == 8_000
    assert sample.gpus[1].temperature_c == 56
    collector.close()
    collector.close()
    assert nvml.init_calls == 1
    assert nvml.shutdown_calls == 1
    with pytest.raises(RuntimeError, match="closed"):
        collector.sample()


def test_no_devices_is_explicit_and_can_recover():
    nvml = FakeNVML()
    nvml.count = 0
    collector = TelemetryCollector(psutil_module=FakePsutil(), nvml_module=nvml)
    sample = collector.sample()
    assert sample.gpus == ()
    assert "no NVIDIA devices" in sample.gpu_status
    nvml.count = 1
    assert len(collector.sample().gpus) == 1
    collector.close()


def test_unsupported_metric_stays_none_and_preserves_other_metrics():
    nvml = FakeNVML()

    def unsupported(handle):
        raise RuntimeError("Not Supported")

    nvml.nvmlDeviceGetUtilizationRates = unsupported
    collector = TelemetryCollector(psutil_module=FakePsutil(), nvml_module=nvml)
    sample = collector.sample()
    assert sample.gpus[0].utilization_percent is None
    assert sample.gpus[0].memory_used_bytes == 2_000
    assert sample.gpus[0].temperature_c == 55
    assert "partial" in sample.gpu_status
    assert "Not Supported" in sample.gpu_status
    collector.close()


def test_hardware_removed_does_not_crash_or_return_stale_measurements():
    nvml = FakeNVML()
    collector = TelemetryCollector(psutil_module=FakePsutil(), nvml_module=nvml)
    assert collector.sample().gpus

    def removed():
        raise RuntimeError("GPU is lost")

    nvml.nvmlDeviceGetCount = removed
    sample = collector.sample()
    assert sample.gpus == ()
    assert "GPU is lost" in sample.gpu_status
    assert sample.cpu_percent == 37.5
    collector.close()


def test_one_inaccessible_gpu_does_not_hide_other_devices():
    nvml = FakeNVML()

    def handle(index):
        if index == 0:
            raise RuntimeError("No Permission")
        return index

    nvml.nvmlDeviceGetHandleByIndex = handle
    collector = TelemetryCollector(psutil_module=FakePsutil(), nvml_module=nvml)
    sample = collector.sample()
    assert [gpu.index for gpu in sample.gpus] == [1]
    assert "No Permission" in sample.gpu_status
    collector.close()


def test_cpu_failure_does_not_hide_ram_and_recovery_primes_again():
    psutil = FakePsutil()
    original = psutil.cpu_percent

    def unavailable(*, interval):
        raise OSError("CPU unavailable")

    psutil.cpu_percent = unavailable
    collector = TelemetryCollector(psutil_module=psutil, nvml_module=None)
    sample = collector.sample()
    assert sample.cpu_percent is None
    assert "CPU unavailable" in sample.cpu_status
    assert sample.ram_percent == 25
    psutil.cpu_percent = original
    assert collector.sample().cpu_percent is None
    assert collector.sample().cpu_percent == 37.5


def test_ram_failure_does_not_hide_cpu():
    psutil = FakePsutil()

    def unavailable():
        raise OSError("RAM unavailable")

    psutil.virtual_memory = unavailable
    collector = TelemetryCollector(psutil_module=psutil, nvml_module=None)
    collector.sample()
    sample = collector.sample()
    assert sample.cpu_percent == 37.5
    assert sample.ram_percent is None
    assert sample.ram_used_bytes is None
    assert sample.ram_total_bytes is None
    assert sample.ram_available_bytes is None
    assert "RAM unavailable" in sample.ram_status


def test_shutdown_failure_is_safe():
    nvml = FakeNVML()

    def removed():
        raise RuntimeError("Driver disappeared")

    nvml.nvmlShutdown = removed
    collector = TelemetryCollector(psutil_module=FakePsutil(), nvml_module=nvml)
    collector.sample()
    collector.close()
    collector.close()
