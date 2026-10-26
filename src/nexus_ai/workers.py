"""Qt worker adapters; HTTP and hardware reads never run on the UI thread."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QTimer, Signal, Slot

from nexus_ai.ollama import OllamaClient
from nexus_ai.profiles import InferencePolicy
from nexus_ai.telemetry import TelemetryCollector


class JobSignals(QObject):
    result = Signal(object, object)
    chunk = Signal(object, str)
    failed = Signal(object, str)
    finished = Signal(object)


class OllamaJob(QRunnable):
    def __init__(
        self,
        kind: str,
        base_url: str,
        client_factory: Callable[..., OllamaClient],
        *,
        model: str = "",
        messages: list[dict[str, str]] | None = None,
        policy: InferencePolicy | None = None,
    ) -> None:
        super().__init__()
        self.kind = kind
        self.base_url = base_url
        self.client_factory = client_factory
        self.model = model
        self.messages = messages or []
        self.policy = policy
        self.cancel_event = Event()
        self.signals = JobSignals()

    @Slot()
    def run(self) -> None:
        try:
            if self.cancel_event.is_set():
                if self.kind == "chat":
                    self.signals.result.emit(self, None)
                return
            with self.client_factory(self.base_url) as client:
                if self.kind == "models":
                    self.signals.result.emit(self, client.list_models())
                else:
                    assert self.policy is not None
                    for chunk in client.stream_chat(
                        self.model,
                        self.messages,
                        options=self.policy.options,
                        keep_alive=self.policy.keep_alive,
                        cancel_event=self.cancel_event,
                    ):
                        if self.cancel_event.is_set():
                            break
                        self.signals.chunk.emit(self, chunk)
                    self.signals.result.emit(self, None)
        except Exception as exc:
            self.signals.failed.emit(self, str(exc) or type(exc).__name__)
        finally:
            self.signals.finished.emit(self)


class TelemetryWorker(QObject):
    sampled = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, collector_factory: Callable[[], TelemetryCollector]) -> None:
        super().__init__()
        self._factory = collector_factory
        self._collector: TelemetryCollector | None = None
        self._timer: QTimer | None = None
        self._interval = 1000

    @Slot()
    def start(self) -> None:
        try:
            self._collector = self._factory()
        except Exception as exc:
            self.failed.emit(str(exc) or type(exc).__name__)
            self.finished.emit()
            return
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll)
        self._timer.start(self._interval)
        self.poll()

    @Slot()
    def poll(self) -> None:
        if self._collector is None:
            return
        try:
            self.sampled.emit(self._collector.sample())
        except Exception as exc:
            self.failed.emit(str(exc) or type(exc).__name__)

    @Slot(int)
    def set_interval(self, interval: int) -> None:
        self._interval = max(250, interval)
        if self._timer is not None and self._timer.interval() != self._interval:
            self._timer.setInterval(self._interval)

    @Slot()
    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        try:
            if self._collector is not None:
                self._collector.close()
        except Exception as exc:
            self.failed.emit(str(exc) or type(exc).__name__)
        finally:
            self._collector = None
            self.finished.emit()
