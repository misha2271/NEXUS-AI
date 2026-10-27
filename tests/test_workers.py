"""Exercise worker signal delivery and resource ownership using real Qt threads."""

from __future__ import annotations

from threading import get_ident

import pytest
from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from nexus_ai.workers import TelemetryWorker


class _Controls(QObject):
    poll = Signal()
    interval = Signal(int)
    stop = Signal()


class _Observer(QObject):
    """Keep queued main-thread slots connected for the whole thread lifetime.

    Disconnecting a temporary pytest-qt waiter from a terminal signal can
    deadlock PySide6 on Windows while the worker is concurrently being deleted.
    These receivers outlive the worker and require no signal-time disconnect.
    """

    def __init__(self):
        super().__init__()
        self.samples = []
        self.errors = []
        self.finished_count = 0
        self.callback_threads = []

    @Slot(object)
    def sampled(self, value):
        self.callback_threads.append(get_ident())
        self.samples.append(value)

    @Slot(str)
    def failed(self, message):
        self.callback_threads.append(get_ident())
        self.errors.append(message)

    @Slot()
    def finished(self):
        self.callback_threads.append(get_ident())
        self.finished_count += 1


class _WorkerThread:
    def __init__(self, qtbot, factory, interval=1000):
        self.qtbot = qtbot
        self.thread = QThread()
        self.worker = TelemetryWorker(factory)
        self.worker.set_interval(interval)
        self.worker.moveToThread(self.thread)
        self.controls = _Controls()
        self.observer = _Observer()
        self._started = False
        self.controls.poll.connect(self.worker.poll)
        self.controls.interval.connect(self.worker.set_interval)
        self.controls.stop.connect(self.worker.stop)
        self.thread.started.connect(self.worker.start)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        queued = Qt.ConnectionType.QueuedConnection
        self.worker.sampled.connect(self.observer.sampled, queued)
        self.worker.failed.connect(self.observer.failed, queued)
        self.thread.finished.connect(self.observer.finished, queued)

    def start(self):
        self._started = True
        self.thread.start()

    def stop(self):
        if self.thread.isRunning():
            self.controls.stop.emit()
        if self._started:
            self.qtbot.waitUntil(
                lambda: self.observer.finished_count > 0 and not self.thread.isRunning(),
                timeout=2000,
            )
            assert self.observer.finished_count == 1
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
    harness.start()
    qtbot.waitUntil(lambda: bool(harness.observer.samples), timeout=2000)
    assert harness.observer.samples == [snapshot]
    assert harness.thread.isRunning()
    harness.stop()
    assert [event for event, _thread in lifecycle] == ["initialize", "sample", "close"]
    assert len({thread for _event, thread in lifecycle}) == 1
    assert lifecycle[0][1] != main_thread
    assert set(harness.observer.callback_threads) == {main_thread}
    assert not harness.thread.isRunning()


def test_initialization_failure_reports_error_and_exits_thread(qtbot, worker_threads):
    attempts = []

    def denied_collector():
        attempts.append(get_ident())
        raise PermissionError("sensor access denied")

    harness = worker_threads(denied_collector)
    harness.start()
    qtbot.waitUntil(
        lambda: (
            bool(harness.observer.errors)
            and harness.observer.finished_count == 1
            and not harness.thread.isRunning()
        ),
        timeout=2000,
    )
    assert harness.observer.errors == ["sensor access denied"]
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
    harness.start()
    qtbot.waitUntil(lambda: bool(harness.observer.errors), timeout=2000)
    assert harness.observer.errors == ["temporary sensor read failure"]
    assert harness.thread.isRunning()
    qtbot.waitUntil(lambda: bool(harness.observer.samples), timeout=2000)
    assert harness.observer.samples[0] is snapshot
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
    harness.start()
    qtbot.waitUntil(lambda: bool(harness.observer.samples), timeout=2000)
    assert harness.observer.samples == [5000]
    for requested, expected in [(1, 250), (2000, 2000)]:
        previous_count = len(harness.observer.samples)
        harness.controls.interval.emit(requested)
        harness.controls.poll.emit()
        qtbot.waitUntil(
            lambda previous_count=previous_count: len(harness.observer.samples) > previous_count,
            timeout=2000,
        )
        assert harness.observer.samples[-1] == expected
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
    harness.start()
    qtbot.waitUntil(lambda: bool(harness.observer.errors), timeout=2000)
    assert harness.observer.errors == ["RuntimeError"]
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
    harness.start()
    qtbot.waitUntil(lambda: bool(harness.observer.samples), timeout=2000)
    harness.stop()
    qtbot.waitUntil(lambda: bool(harness.observer.errors), timeout=2000)
    assert harness.observer.errors == ["sensor disappeared during shutdown"]
    assert len(closed) == 1
    assert not harness.thread.isRunning()
