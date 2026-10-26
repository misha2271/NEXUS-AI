"""v0.4 history, temperatures, responsive navigation, and streaming regressions."""

from __future__ import annotations

import math
from dataclasses import replace
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt, QTimer

from nexus_ai.history import TelemetryHistory
from nexus_ai.modules import MODULES, IntegrationRegistry, IntegrationStatus
from nexus_ai.settings import SettingsStore
from nexus_ai.telemetry import GPUReading, TelemetryCollector, TelemetrySnapshot
from nexus_ai.ui.window import MainWindow
from nexus_ai.workers import OllamaJob, TelemetryWorker


def sample(timestamp=1, **changes):
    snapshot = TelemetrySnapshot(30, 40, 4, 10, 6, (), "No NVIDIA driver", sampled_at=timestamp)
    return replace(snapshot, **changes)


def test_history_is_bounded_by_time_and_point_count_and_keeps_gaps():
    history = TelemetryHistory(max_points=3, seconds=5)
    history.append(sample(0))
    history.append(sample(1, cpu_percent=None))
    history.append(sample(2))
    assert history.series("cpu") == [(0, 30), (1, None), (2, 30)]
    history.append(sample(3))
    assert [point.timestamp for point in history.points] == [1, 2, 3]
    history.append(sample(10))
    assert history.series("cpu") == [(10, 30)]
    with pytest.raises(ValueError, match="monotonic"):
        history.append(sample(9))
    with pytest.raises(ValueError, match="finite"):
        history.append(sample(math.nan))


def test_history_preserves_each_gpu_and_marks_removed_devices_missing():
    history = TelemetryHistory()
    gpu0 = GPUReading(0, "zero", 50, 2, 8, 65)
    gpu1 = GPUReading(1, "one", None, None, None, None)
    history.append(sample(1, gpus=(gpu0, gpu1)))
    history.append(sample(2))
    assert history.series("gpu:0") == [(1, 50), (2, None)]
    assert history.series("vram:0") == [(1, 25), (2, None)]
    assert history.series("vram:1") == [(1, None), (2, None)]
    assert history.series("gpu_temp:0") == [(1, 65), (2, None)]
    assert history.keys("gpu:") == ["gpu:0", "gpu:1"]
    history.append_values(3, {"cpu": math.inf})
    assert history.series("cpu")[-1] == (3, None)


def test_named_temperatures_use_real_backend_and_ignore_missing_or_nonfinite_readings():
    calls = []

    def sensors(**kwargs):
        calls.append(kwargs)
        return {
            "coretemp": [
                SimpleNamespace(label="Package id 0", current=54.5),
                SimpleNamespace(label="", current=None),
                SimpleNamespace(label="Invalid", current=math.nan),
            ]
        }

    backend = SimpleNamespace(sensors_temperatures=sensors)
    collector = TelemetryCollector(psutil_module=backend, nvml_module=None)
    result = collector.sample()
    assert calls == [{"fahrenheit": False}]
    assert [(s.name, s.current_c) for s in result.temperatures] == [
        ("coretemp / Package id 0", 54.5)
    ]
    assert "available" in result.temperature_status
    assert result.cpu_percent is None  # temperature access does not fabricate other sensors
    history = TelemetryHistory()
    history.append(result)
    assert history.series("temperature:coretemp / Package id 0")[0][1] == 54.5
    collector.close()


@pytest.mark.parametrize(
    "backend", [SimpleNamespace(), SimpleNamespace(sensors_temperatures=lambda **_: {})]
)
def test_unsupported_or_empty_temperature_backend_is_not_zero(backend):
    result = TelemetryCollector(psutil_module=backend, nvml_module=None).sample()
    assert result.temperatures == ()
    assert "unavailable" in result.temperature_status or "No readable" in result.temperature_status


def test_temperature_permission_failure_preserves_cpu_and_ram():
    def denied(**_):
        raise PermissionError("sensor access denied")

    backend = SimpleNamespace(
        sensors_temperatures=denied,
        cpu_percent=lambda **_: 33,
        virtual_memory=lambda: SimpleNamespace(percent=50, used=4, total=8, available=4),
    )
    collector = TelemetryCollector(psutil_module=backend, nvml_module=None)
    collector.sample()
    result = collector.sample()
    assert result.cpu_percent == 33 and result.ram_percent == 50
    assert result.temperatures == ()
    assert "sensor access denied" in result.temperature_status


@pytest.fixture
def dashboard(qtbot, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(replace(store.load(), language="en"))
    window = MainWindow(store, start_background=False)
    qtbot.addWidget(window)
    window.show()
    yield window
    window.close()
    qtbot.waitUntil(lambda: not window.isVisible())


def test_sidebar_routes_and_default_deny_hardware_controls(dashboard, qtbot):
    for spec in MODULES:
        qtbot.mouseClick(
            dashboard.sidebar.buttons[spec.key],
            Qt.MouseButton.LeftButton,
        )
        assert dashboard.stack.currentWidget() is dashboard.pages[spec.key]
        assert dashboard.sidebar.buttons[spec.key].isChecked()
        assert not dashboard.integrations.status(spec.key).available
        assert all(not button.isEnabled() for button in dashboard.module_pages[spec.key].controls)
    assert not dashboard.fan_button.isEnabled()
    dashboard.module_pages["gaming"].gaming_button.click()
    assert dashboard.store.load().profile == "Gaming"
    assert len(dashboard.sidebar.buttons) == 8
    assert sum(button.isChecked() for button in dashboard.sidebar.buttons.values()) == 1
    with pytest.raises(ValueError, match="Unknown workspace"):
        dashboard.navigate("nonexistent")


def test_registry_never_permits_unavailable_or_unvalidated_operations():
    registry = IntegrationRegistry()
    assert not registry.status("rgb").permits("rgb")
    registry.record_probe(
        "rgb", IntegrationStatus(True, False, "not validated", frozenset({"rgb"}))
    )
    assert not registry.status("rgb").permits("rgb")
    registry.record_probe("rgb", IntegrationStatus(False, True, "unplugged", frozenset({"rgb"})))
    assert not registry.status("rgb").permits("rgb")


def test_responsive_reflow_preserves_widgets_and_chat_draft(dashboard, qtbot):
    dashboard.resize(1500, 1000)
    qtbot.waitUntil(lambda: dashboard.metric_grid.columns == 4)
    assert dashboard.chart_grid.columns == 2
    dashboard.prompt.setPlainText("Keep my unfinished question")
    dashboard.resize(760, 680)
    qtbot.waitUntil(lambda: dashboard.chart_grid.columns == 1)
    assert dashboard.metric_grid.columns < 4
    dashboard.navigate("assistant")
    assert dashboard.prompt.toPlainText() == "Keep my unfinished question"
    assert dashboard.prompt.width() > 100
    dashboard.resize(1500, 1000)
    dashboard.navigate("overview")
    qtbot.waitUntil(lambda: dashboard.metric_grid.columns == 4)
    assert dashboard.cpu_card is dashboard.metric_grid.widgets[0]


def test_live_dashboard_tracks_failure_gaps_and_per_device_removal(dashboard):
    from time import monotonic

    first = sample(monotonic(), gpus=(GPUReading(1, "Actual device", 35, 2, 8, 70),))
    dashboard._show_telemetry(first)
    assert dashboard._gpu_cards[1].bar.value() == 35
    assert dashboard.vram_card.bar.value() == 25
    assert dashboard.charts[2].chart_series()[0][-1][1] == 35
    dashboard._telemetry_failed("device lost")
    assert dashboard.history.series("gpu:1")[-1][1] is None
    assert dashboard.vram_card.bar.isHidden()
    dashboard._show_telemetry(sample(monotonic()))
    assert not dashboard._gpu_cards
    assert (
        "unavailable" in dashboard.temperature_values.text().lower()
        or "No host" in dashboard.temperature_values.text()
    )
    # Rendering an unavailable plot must also work on a narrow dashboard.
    assert not dashboard.grab().isNull()


def test_stream_chunks_are_batched_and_flushed_before_completion(dashboard):
    from nexus_ai.profiles import resolve_policy

    job = OllamaJob(
        "chat", "http://localhost:11434", lambda _: None, policy=resolve_policy("Smart")
    )
    dashboard._chat_job = job
    dashboard._pending_user = "Question"
    for chunk in ("one", " two", " three"):
        dashboard._chat_chunk(job, chunk)
    assert dashboard.transcript.toPlainText() == ""
    dashboard._job_result(job, None)
    assert "one two three" in dashboard.transcript.toPlainText()
    assert dashboard._messages[-1]["content"] == "one two three"
    assert not dashboard._pending_chunks
    assert not dashboard._render_timer.isActive()
    dashboard._job_finished(job)


def test_cancelled_discovery_does_not_emit_models_or_errors(qapp):
    results, failures, finished = [], [], []
    job = None

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def list_models(self):
            job.cancel()
            return ["must not escape"]

    job = OllamaJob("models", "http://localhost", lambda _: Client())
    job.signals.result.connect(lambda *args: results.append(args))
    job.signals.failed.connect(lambda *args: failures.append(args))
    job.signals.finished.connect(lambda *args: finished.append(args))
    job.run()
    assert not results and not failures and len(finished) == 1


def test_monitor_stop_is_idempotent_and_does_not_start_after_stop(qapp):
    created, stopped = [], []
    worker = TelemetryWorker(lambda: created.append(True))
    worker.finished.connect(lambda: stopped.append(True))
    worker.stop()
    worker.stop()
    worker.start()
    assert stopped == [True] and not created


def test_slow_worker_cancel_keeps_event_loop_alive(dashboard, qtbot):
    import threading

    entered, release = threading.Event(), threading.Event()
    ticks = []
    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(lambda: ticks.append(True))

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def list_models(self):
            entered.set()
            release.wait(3)
            return []

    dashboard._client_factory = lambda _: Client()
    timer.start()
    dashboard.refresh_models()
    try:
        qtbot.waitUntil(entered.is_set)
        dashboard.close()
        qtbot.waitUntil(lambda: len(ticks) >= 3)
        assert dashboard.isVisible() and dashboard._closing
    finally:
        release.set()
        qtbot.waitUntil(lambda: not dashboard.isVisible(), timeout=4000)
        timer.stop()
    assert not dashboard._jobs and not dashboard._pool.activeThreadCount()


def test_cancelled_chat_transport_failure_completes_as_stop_not_error(qapp):
    from nexus_ai.profiles import resolve_policy

    results, failures, closed = [], [], []
    job = None

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            closed.append(True)

        def stream_chat(self, *_args, **_kwargs):
            job.cancel()
            raise OSError("socket closed while cancelled")
            yield  # make this the same generator interface as the real client

    job = OllamaJob("chat", "http://localhost", lambda _: Client(), policy=resolve_policy("Eco"))
    job.signals.result.connect(lambda *args: results.append(args))
    job.signals.failed.connect(lambda *args: failures.append(args))
    job.run()
    assert closed == [True] and not failures and results == [(job, None)]


def test_cancel_discards_late_chunks_and_preserves_only_rendered_partial_reply(dashboard):
    job = OllamaJob("chat", "http://localhost", lambda _: None)
    dashboard._chat_job = job
    dashboard._pending_user = "question"
    dashboard._chat_chunk(job, "partial")
    dashboard.stop_generation()
    dashboard._chat_chunk(job, "must not appear")
    dashboard._job_result(job, None)
    dashboard._job_finished(job)
    assert "partial" in dashboard.transcript.toPlainText()
    assert "must not appear" not in dashboard.transcript.toPlainText()
    assert dashboard._messages == []
    assert not dashboard._pending_chunks
    assert not dashboard.stop_button.isEnabled()


def test_queued_telemetry_failure_uses_worker_time_not_ui_delivery_time(dashboard):
    dashboard._show_telemetry(sample(10))
    dashboard._telemetry_failed("temporarily disconnected", 11)
    dashboard._show_telemetry(sample(12))
    assert dashboard.history.series("cpu") == [(10, 30), (11, None), (12, 30)]
    dashboard._telemetry_failed("external failure without timestamp")
    dashboard._show_telemetry(sample(13))
    assert dashboard.history.series("cpu")[-2:] == [(12, None), (13, 30)]


def test_worker_failure_carries_monotonic_emission_timestamp(qapp):
    from time import monotonic

    def fail():
        raise PermissionError("sensor denied")

    worker = TelemetryWorker(fail)
    errors = []
    worker.failed_at.connect(lambda *args: errors.append(args))
    before = monotonic()
    worker.start()
    after = monotonic()
    assert errors[0][0] == "sensor denied"
    assert before <= errors[0][1] <= after
