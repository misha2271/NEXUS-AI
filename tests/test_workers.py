"""Exercise worker signal delivery and resource ownership using real Qt threads."""

from __future__ import annotations

from threading import get_ident

import pytest
from PySide6.QtCore import QObject, QThread, Signal

from nexus_ai.workers import TelemetryWorker


class _Controls(QObject):
    poll = Signal()
    interval = Signal(int)
    stop = Signal()


class _WorkerThread:
    def __init__(self, qtbot, factory, interval=1000):
        self.qtbot = qtbot
        self.thread = QThread()
        self.worker = TelemetryWorker(factory)
        self.worker.set_interval(interval)
        self.worker.moveToThread(self.thread)
        self.controls = _Controls()
        self.controls.poll.connect(self.worker.poll)
        self.controls.interval.connect(self.worker.set_interval)
        self.controls.stop.connect(self.worker.stop)
        self.thread.started.connect(self.worker.start)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)

    def start(self):
        self.thread.start()

    def stop(self):
        if self.thread.isRunning():
            with self.qtbot.waitSignal(self.thread.finished, timeout=2000):
                self.controls.stop.emit()
        assert self.thread.wait(2000), "Telemetry thread did not exit"


@pytest.fixture
def worker_threads(qtbot):
    threads = []

    def create(factory, interval=1000):
        harness = _WorkerThread(qtbot, factory, interval)
        threads.append(harness)
        return harness

    yield create
    for harness in threads:
        try:
            harness.stop()
        finally:
            # Never leave a running QThread behind, even after a failed assertion.
            harness.thread.quit()
            assert harness.thread.wait(2000), "Telemetry thread remained running during cleanup"


def test_collector_lifecycle_occurs_on_worker_thread(qtbot, worker_threads):
    lifecycle = []
    snapshot = object()
    main_thread = get_ident()

    class Collector:
        def __init__(self):
            lifecycle.append(("initialize", get_ident()))

        def sample(self):
            lifecycle.append(("sample", get_ident()))
            return snapshot

        def close(self):
            lifecycle.append(("close", get_ident()))

    harness = worker_threads(Collector, interval=5000)
    with qtbot.waitSignal(harness.worker.sampled, timeout=2000) as sampled:
        harness.start()
    assert sampled.args == [snapshot]
    assert harness.thread.isRunning()
    harness.stop()
    assert [event for event, _thread in lifecycle] == ["initialize", "sample", "close"]
    assert len({thread for _event, thread in lifecycle}) == 1
    assert lifecycle[0][1] != main_thread
    assert not harness.thread.isRunning()


def test_initialization_failure_reports_error_and_exits_thread(qtbot, worker_threads):
    attempts = []

    def denied_collector():
        attempts.append(get_ident())
        raise PermissionError("sensor access denied")

    harness = worker_threads(denied_collector)
    with qtbot.waitSignal(harness.thread.finished, timeout=2000):
        with qtbot.waitSignal(harness.worker.failed, timeout=2000) as failed:
            harness.start()
    assert failed.args == ["sensor access denied"]
    assert len(attempts) == 1
    assert not harness.thread.isRunning()


def test_sample_failure_keeps_timer_alive_and_recovers(qtbot, worker_threads):
    reads = []
    closed = []
    snapshot = object()

    class Collector:
        def sample(self):
            reads.append(get_ident())
            if len(reads) == 1:
                raise RuntimeError("temporary sensor read failure")
            return snapshot

        def close(self):
            closed.append(get_ident())

    harness = worker_threads(Collector, interval=250)
    with qtbot.waitSignal(harness.worker.sampled, timeout=2000) as sampled:
        with qtbot.waitSignal(harness.worker.failed, timeout=2000) as failed:
            harness.start()
        assert failed.args == ["temporary sensor read failure"]
        assert harness.thread.isRunning()
    assert sampled.args == [snapshot]
    assert len(reads) >= 2
    harness.stop()
    assert closed == [reads[0]]


def test_interval_changes_are_queued_and_clamped_on_worker_thread(qtbot, worker_threads):
    intervals = []
    instances = []
    harness = None

    class Collector:
        def __init__(self):
            instances.append(self)

        def sample(self):
            interval = harness.worker._timer.interval()
            intervals.append(interval)
            return interval

        def close(self):
            pass

    harness = worker_threads(Collector, interval=5000)
    with qtbot.waitSignal(harness.worker.sampled, timeout=2000) as initial:
        harness.start()
    assert initial.args == [5000]
    for requested, expected in [(1, 250), (2000, 2000)]:
        with qtbot.waitSignal(harness.worker.sampled, timeout=2000) as sampled:
            harness.controls.interval.emit(requested)
            harness.controls.poll.emit()
        assert sampled.args == [expected]
    assert intervals == [5000, 250, 2000]
    assert len(instances) == 1
    harness.stop()


def test_empty_sensor_error_uses_exception_type(qtbot, worker_threads):
    class Collector:
        def sample(self):
            raise RuntimeError()

        def close(self):
            pass

    harness = worker_threads(Collector, interval=5000)
    with qtbot.waitSignal(harness.worker.failed, timeout=2000) as failed:
        harness.start()
    assert failed.args == ["RuntimeError"]
    harness.stop()


def test_shutdown_error_reports_failure_and_still_exits_thread(qtbot, worker_threads):
    closed = []

    class Collector:
        def sample(self):
            return object()

        def close(self):
            closed.append(get_ident())
            raise RuntimeError("sensor disappeared during shutdown")

    harness = worker_threads(Collector, interval=5000)
    with qtbot.waitSignal(harness.worker.sampled, timeout=2000):
        harness.start()
    with qtbot.waitSignal(harness.worker.failed, timeout=2000) as failed:
        harness.stop()
    assert failed.args == ["sensor disappeared during shutdown"]
    assert len(closed) == 1
    assert not harness.thread.isRunning()
