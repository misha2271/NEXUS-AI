"""Serial worker operations with Qt-thread delivery and nonblocking shutdown."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from nexus_ai.i18n import error_text


class _Signals(QObject):
    result = Signal(object, object)
    failed = Signal(object, object)
    finished = Signal(object)


class _Task(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = _Signals()

    @Slot()
    def run(self):
        try:
            self.signals.result.emit(self, self.operation())
        except Exception as exc:
            self.signals.failed.emit(self, error_text(exc))
        finally:
            self.signals.finished.emit(self)


class TaskRunner(QObject):
    """Complete queued writes in order, including while a window is closing.

    The owner must keep this object alive until ``busy`` becomes false. No
    ``waitForDone`` or worker-thread UI callbacks are used.
    """

    failed = Signal(object)
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._tasks = {}
        self._closing = False

    @property
    def busy(self):
        return bool(self._tasks) or self.pool.activeThreadCount() > 0

    @property
    def pending(self):
        return bool(self._tasks)

    def submit(self, operation, done=None):
        if self._closing:
            return False
        task = _Task(operation)
        self._tasks[task] = done
        task.signals.result.connect(self._result)
        task.signals.failed.connect(self._failed)
        task.signals.finished.connect(self._finished)
        self.busy_changed.emit(True)
        self.pool.start(task)
        return True

    @Slot(object, object)
    def _result(self, task, result):
        callback = self._tasks.get(task)
        if callback is not None:
            callback(result)

    @Slot(object, object)
    def _failed(self, task, error):
        self.failed.emit(error)

    @Slot(object)
    def _finished(self, task):
        self._tasks.pop(task, None)
        self.busy_changed.emit(bool(self._tasks))

    def shutdown(self):
        self._closing = True
