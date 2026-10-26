"""Application-level inference budgets; these do not alter OS or GPU clocks."""

from __future__ import annotations

import os
from dataclasses import dataclass

PROFILE_NAMES = ("Smart", "Maximum AI", "Gaming", "Eco")
_GIB = 1024**3


@dataclass(frozen=True)
class InferencePolicy:
    """Options sent to Ollama and the application's telemetry polling interval."""

    options: dict[str, int]
    keep_alive: str | int
    description: str
    monitor_interval_ms: int


def resolve_policy(
    profile: str,
    cpu_count: int | None = None,
    cpu_percent: float = 0,
    ram_available_bytes: int | None = None,
) -> InferencePolicy:
    """Resolve a budget when a request starts, using currently available resources.

    Smart leaves room for other work and reduces its context/thread budget under
    CPU or memory pressure. Maximum AI lets Ollama choose GPU offload. Gaming and
    Eco request CPU-only inference and unload the model after the response. These
    are real Ollama options, not claims to change Windows power plans, process
    priority, hardware fan speeds, clocks, or driver settings.
    """
    if profile not in PROFILE_NAMES:
        raise ValueError(f"Unknown performance profile: {profile}")
    count = cpu_count if isinstance(cpu_count, int) and cpu_count > 0 else os.cpu_count()
    count = max(1, count or 1)
    if profile == "Maximum AI":
        return InferencePolicy(
            options={"num_thread": max(1, count - 1), "num_ctx": 8192},
            keep_alive="10m",
            description="Larger context and CPU budget; Ollama selects GPU offload.",
            monitor_interval_ms=1000,
        )
    if profile == "Gaming":
        return InferencePolicy(
            options={"num_thread": min(2, count), "num_ctx": 2048, "num_gpu": 0},
            keep_alive=0,
            description="CPU-only inference with up to two threads; unload after each response.",
            monitor_interval_ms=2000,
        )
    if profile == "Eco":
        return InferencePolicy(
            options={"num_thread": 1, "num_ctx": 2048, "num_gpu": 0},
            keep_alive=0,
            description=(
                "One CPU thread, smaller context, slower monitoring; unload after each response."
            ),
            monitor_interval_ms=5000,
        )
    memory_pressure = ram_available_bytes is not None and ram_available_bytes < 4 * _GIB
    under_pressure = cpu_percent >= 80 or memory_pressure
    return InferencePolicy(
        options={
            "num_thread": max(1, count // (4 if under_pressure else 2)),
            "num_ctx": 2048 if under_pressure else 4096,
        },
        keep_alive=0 if memory_pressure else "5m",
        description=(
            "Resource pressure detected: reduced thread/context budget."
            if under_pressure
            else "Balanced CPU budget; Ollama selects GPU offload."
        ),
        monitor_interval_ms=2000 if under_pressure else 1000,
    )
