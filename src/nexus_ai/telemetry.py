"""Non-blocking host telemetry with an optional NVIDIA NVML backend.

The collector is intended for serialized calls from a worker thread. Missing
hardware and unsupported metrics are represented by ``None``, never invented
measurements. The first CPU sample only primes psutil's interval counter.
"""

from __future__ import annotations

import importlib
import math
import time
from dataclasses import dataclass, field
from typing import Any

import psutil

from nexus_ai.i18n import JoinedText, Text

_AUTO = object()


@dataclass(frozen=True)
class GPUReading:
    index: int
    name: str
    utilization_percent: float | None
    memory_used_bytes: int | None
    memory_total_bytes: int | None
    temperature_c: float | None


@dataclass(frozen=True)
class TemperatureReading:
    name: str
    current_c: float


@dataclass(frozen=True)
class TelemetrySnapshot:
    cpu_percent: float | None
    ram_percent: float | None
    ram_used_bytes: int | None
    ram_total_bytes: int | None
    ram_available_bytes: int | None
    gpus: tuple[GPUReading, ...]
    gpu_status: str
    cpu_status: str = "CPU telemetry available"
    ram_status: str = "RAM telemetry available"
    temperatures: tuple[TemperatureReading, ...] = ()
    temperature_status: str = "Temperature sensors unavailable on this platform"
    sampled_at: float = field(default_factory=time.monotonic)


class TelemetryCollector:
    """Read psutil and NVML without blocking on measurement intervals.

    NVML is imported and initialized lazily. The optional constructor arguments
    allow deterministic tests without requiring NVIDIA hardware or drivers.
    Failed NVML initialization is not retried continuously; create a new
    collector after installing a driver or the optional package.
    """

    def __init__(self, *, psutil_module: Any = None, nvml_module: Any = _AUTO):
        self._psutil = psutil if psutil_module is None else psutil_module
        self._nvml = nvml_module
        self._nvml_attempted = False
        self._nvml_initialized = False
        self._gpu_status = "NVIDIA telemetry not initialized"
        self._cpu_primed = False
        self._closed = False

    def sample(self) -> TelemetrySnapshot:
        if self._closed:
            raise RuntimeError(Text("Telemetry collector is closed"))

        cpu_percent = None
        cpu_status = "Collecting first CPU sample"
        try:
            value = self._psutil.cpu_percent(interval=None)
            if self._cpu_primed:
                cpu_percent = float(value)
                cpu_status = "CPU telemetry available"
            self._cpu_primed = True
        except Exception as exc:
            self._cpu_primed = False
            cpu_status = Text("CPU telemetry unavailable: {error}", error=_error_text(exc))

        ram_percent = ram_used = ram_total = ram_available = None
        ram_status = "RAM telemetry available"
        try:
            memory = self._psutil.virtual_memory()
            ram_percent = float(memory.percent)
            ram_used = int(memory.used)
            ram_total = int(memory.total)
            ram_available = int(memory.available)
        except Exception as exc:
            ram_status = Text("RAM telemetry unavailable: {error}", error=_error_text(exc))

        gpus = self._sample_gpus()
        temperatures, temperature_status = self._sample_temperatures()
        return TelemetrySnapshot(
            cpu_percent=cpu_percent,
            ram_percent=ram_percent,
            ram_used_bytes=ram_used,
            ram_total_bytes=ram_total,
            ram_available_bytes=ram_available,
            gpus=gpus,
            gpu_status=self._gpu_status,
            cpu_status=cpu_status,
            ram_status=ram_status,
            temperatures=temperatures,
            temperature_status=temperature_status,
        )

    def _sample_temperatures(self) -> tuple[tuple[TemperatureReading, ...], str]:
        reader = getattr(self._psutil, "sensors_temperatures", None)
        if reader is None:
            return (), "Host temperature sensors unavailable on this platform"
        try:
            sensors = reader(fahrenheit=False)
            readings = []
            for group, entries in sensors.items():
                for index, entry in enumerate(entries):
                    value = entry.current
                    if value is not None and math.isfinite(value):
                        label = entry.label or Text("Sensor {index}", index=index + 1)
                        readings.append(
                            TemperatureReading(
                                Text("{group} / {label}", group=group, label=label), float(value)
                            )
                        )
            status = (
                "Host temperature sensors available"
                if readings
                else "No readable host temperature sensors"
            )
            return tuple(readings), status
        except Exception as exc:
            return (), Text("Host temperature sensors unavailable: {error}", error=_error_text(exc))

    def _initialize_nvml(self) -> None:
        self._nvml_attempted = True
        if self._nvml is _AUTO:
            try:
                self._nvml = importlib.import_module("pynvml")
            except ImportError:
                self._gpu_status = (
                    "NVIDIA telemetry unavailable: optional nvidia-ml-py package is not installed"
                )
                return
            except Exception as exc:
                self._gpu_status = Text(
                    "NVIDIA telemetry unavailable: {error}", error=_error_text(exc)
                )
                return
        if self._nvml is None:
            self._gpu_status = (
                "NVIDIA telemetry unavailable: optional nvidia-ml-py package is not installed"
            )
            return
        try:
            self._nvml.nvmlInit()
            self._nvml_initialized = True
        except Exception as exc:
            self._gpu_status = Text(
                "NVIDIA telemetry unavailable (NVML/driver): {error}", error=_error_text(exc)
            )

    def _sample_gpus(self) -> tuple[GPUReading, ...]:
        if not self._nvml_attempted:
            self._initialize_nvml()
        if not self._nvml_initialized:
            return ()

        try:
            count = self._nvml.nvmlDeviceGetCount()
        except Exception as exc:
            self._gpu_status = Text("NVIDIA telemetry unavailable: {error}", error=_error_text(exc))
            return ()
        if count == 0:
            self._gpu_status = "NVIDIA telemetry unavailable: no NVIDIA devices detected"
            return ()

        readings: list[GPUReading] = []
        failures: list[str] = []
        for index in range(count):
            try:
                handle = self._nvml.nvmlDeviceGetHandleByIndex(index)
                name = self._nvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8", errors="replace")
            except Exception as exc:
                failures.append(Text("GPU {index}: {error}", index=index, error=_error_text(exc)))
                continue

            utilization = memory_used = memory_total = temperature = None
            try:
                utilization = float(self._nvml.nvmlDeviceGetUtilizationRates(handle).gpu)
            except Exception as exc:
                failures.append(
                    Text("GPU {index} utilization: {error}", index=index, error=_error_text(exc))
                )
            try:
                memory = self._nvml.nvmlDeviceGetMemoryInfo(handle)
                memory_used, memory_total = int(memory.used), int(memory.total)
            except Exception as exc:
                failures.append(
                    Text("GPU {index} memory: {error}", index=index, error=_error_text(exc))
                )
            try:
                temperature = float(
                    self._nvml.nvmlDeviceGetTemperature(handle, self._nvml.NVML_TEMPERATURE_GPU)
                )
            except Exception as exc:
                failures.append(
                    Text("GPU {index} temperature: {error}", index=index, error=_error_text(exc))
                )
            readings.append(
                GPUReading(
                    index=index,
                    name=str(name),
                    utilization_percent=utilization,
                    memory_used_bytes=memory_used,
                    memory_total_bytes=memory_total,
                    temperature_c=temperature,
                )
            )

        if failures:
            state = "partial" if readings else "unavailable"
            self._gpu_status = Text(
                "NVIDIA telemetry {state}: {errors}",
                state=Text(state),
                errors=JoinedText(failures, "; "),
            )
        else:
            self._gpu_status = Text(
                "NVIDIA telemetry available ({count} device(s))", count=len(readings)
            )
        return tuple(readings)

    def close(self) -> None:
        """Release a successfully acquired NVML reference, once."""
        if self._closed:
            return
        self._closed = True
        if self._nvml_initialized:
            self._nvml_initialized = False
            try:
                self._nvml.nvmlShutdown()
            except Exception:
                # Driver disappearance during shutdown must not prevent exit.
                pass


def _error_text(exc: Exception) -> str:
    return str(exc).strip() or type(exc).__name__
