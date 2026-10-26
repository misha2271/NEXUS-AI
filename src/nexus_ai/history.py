"""Bounded, timestamped telemetry history. Missing readings remain chart gaps."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from nexus_ai.telemetry import TelemetrySnapshot


@dataclass(frozen=True)
class HistoryPoint:
    timestamp: float
    values: dict[str, float | None]


class TelemetryHistory:
    def __init__(self, *, max_points: int = 300, seconds: float = 600) -> None:
        if max_points < 2 or seconds <= 0:
            raise ValueError("History needs at least two points and a positive duration")
        self.points: deque[HistoryPoint] = deque(maxlen=max_points)
        self.seconds = seconds

    def append(self, snapshot: TelemetrySnapshot) -> None:
        values = {"cpu": snapshot.cpu_percent, "ram": snapshot.ram_percent}
        for gpu in snapshot.gpus:
            prefix = f"gpu:{gpu.index}"
            values[prefix] = gpu.utilization_percent
            values[f"vram:{gpu.index}"] = (
                100 * gpu.memory_used_bytes / gpu.memory_total_bytes
                if gpu.memory_used_bytes is not None and gpu.memory_total_bytes
                else None
            )
            values[f"gpu_temp:{gpu.index}"] = gpu.temperature_c
        for sensor in snapshot.temperatures:
            values[f"temperature:{sensor.name}"] = sensor.current_c
        self.append_values(snapshot.sampled_at, values)

    def append_values(self, timestamp: float, values: dict[str, float | None]) -> None:
        if not math.isfinite(timestamp):
            raise ValueError("History timestamp must be finite")
        if self.points and timestamp < self.points[-1].timestamp:
            raise ValueError("History timestamps must be monotonic")
        clean = {
            key: float(value) if value is not None and math.isfinite(value) else None
            for key, value in values.items()
        }
        self.points.append(HistoryPoint(timestamp, clean))
        while self.points and timestamp - self.points[0].timestamp > self.seconds:
            self.points.popleft()

    def series(self, key: str) -> list[tuple[float, float | None]]:
        return [(point.timestamp, point.values.get(key)) for point in self.points]

    def keys(self, prefix: str) -> list[str]:
        return sorted(
            {key for point in self.points for key in point.values if key.startswith(prefix)}
        )
