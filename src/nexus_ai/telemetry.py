"""Non-blocking host telemetry with an optional NVIDIA NVML backend.

The collector is intended for serialized calls from a worker thread. Missing
hardware and unsupported metrics are represented by ``None``, never invented
measurements. The first CPU sample only primes psutil's interval counter.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

import psutil

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
            raise RuntimeError("Telemetry collector is closed")

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
            cpu_status = f"CPU telemetry unavailable: {_error_text(exc)}"

        ram_percent = ram_used = ram_total = ram_available = None
        ram_status = "RAM telemetry available"
        try:
            memory = self._psutil.virtual_memory()
            ram_percent = float(memory.percent)
            ram_used = int(memory.used)
            ram_total = int(memory.total)
            ram_available = int(memory.available)
        except Exception as exc:
            ram_status = f"RAM telemetry unavailable: {_error_text(exc)}"

        gpus = self._sample_gpus()
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
        )

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
                self._gpu_status = f"NVIDIA telemetry unavailable: {_error_text(exc)}"
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
            self._gpu_status = "NVIDIA telemetry unavailable (NVML/driver): " + _error_text(exc)

    def _sample_gpus(self) -> tuple[GPUReading, ...]:
        if not self._nvml_attempted:
            self._initialize_nvml()
        if not self._nvml_initialized:
            return ()

        try:
            count = self._nvml.nvmlDeviceGetCount()
        except Exception as exc:
            self._gpu_status = f"NVIDIA telemetry unavailable: {_error_text(exc)}"
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
                failures.append(f"GPU {index}: {_error_text(exc)}")
                continue

            utilization = memory_used = memory_total = temperature = None
            try:
                utilization = float(self._nvml.nvmlDeviceGetUtilizationRates(handle).gpu)
            except Exception as exc:
                failures.append(f"GPU {index} utilization: {_error_text(exc)}")
            try:
                memory = self._nvml.nvmlDeviceGetMemoryInfo(handle)
                memory_used, memory_total = int(memory.used), int(memory.total)
            except Exception as exc:
                failures.append(f"GPU {index} memory: {_error_text(exc)}")
            try:
                temperature = float(
                    self._nvml.nvmlDeviceGetTemperature(handle, self._nvml.NVML_TEMPERATURE_GPU)
                )
            except Exception as exc:
                failures.append(f"GPU {index} temperature: {_error_text(exc)}")
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
            self._gpu_status = f"NVIDIA telemetry {state}: " + "; ".join(failures)
        else:
            self._gpu_status = f"NVIDIA telemetry available ({len(readings)} device(s))"
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
