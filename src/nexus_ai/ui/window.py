"""Desktop chat and live hardware dashboard."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from PySide6.QtCore import Qt, QThread, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from nexus_ai.ollama import OllamaClient
from nexus_ai.profiles import PROFILE_NAMES, InferencePolicy, resolve_policy
from nexus_ai.settings import Settings, SettingsStore, validate_settings
from nexus_ai.telemetry import TelemetryCollector, TelemetrySnapshot
from nexus_ai.workers import OllamaJob, TelemetryWorker

_STYLE = """
QWidget { background: #10151f; color: #edf2f7; font-family: 'Segoe UI', sans-serif;
          font-size: 13px; }
QLabel#title { font-size: 25px; font-weight: 700; color: #a5b4fc; }
QLabel#subtitle, QLabel#muted { color: #a6b2c7; }
QFrame#panel { background: #172031; border: 1px solid #2a354b; border-radius: 10px; }
QFrame#panel QLabel { background: transparent; }
QPlainTextEdit, QLineEdit, QComboBox { background: #0b1019; border: 1px solid #36445f;
    border-radius: 6px; padding: 8px; selection-background-color: #4263eb; }
QPlainTextEdit:focus, QLineEdit:focus, QComboBox:focus { border-color: #818cf8; }
QPushButton { background: #283650; border: 1px solid #3c4c69; border-radius: 6px;
              padding: 8px 14px; }
QPushButton:hover { background: #35476b; }
QPushButton#primary { background: #4f46e5; border-color: #6366f1; }
QPushButton:disabled { color: #78849b; background: #1b2434; border-color: #283246; }
QProgressBar { background: #0b1019; border: 0; border-radius: 4px; height: 9px; }
QProgressBar::chunk { background: #818cf8; border-radius: 4px; }
QSplitter::handle { background: #263248; }
QScrollArea { border: 0; }
"""


def _gib(value: int | None) -> str:
    return "Unavailable" if value is None else f"{value / 1024**3:.1f} GiB"


class MetricCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("panel")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
        self.value = QLabel("Waiting for telemetry…")
        self.value.setWordWrap(True)
        layout.addWidget(self.value)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.hide()
        layout.addWidget(self.bar)

    def update_metric(self, percent: float | None, detail: str) -> None:
        self.value.setText(detail)
        self.bar.setVisible(percent is not None)
        if percent is not None:
            self.bar.setValue(round(percent))


class MainWindow(QMainWindow):
    monitor_interval_changed = Signal(int)
    monitor_stop_requested = Signal()

    def __init__(
        self,
        store: SettingsStore,
        *,
        client_factory: Callable[..., OllamaClient] = OllamaClient,
        collector_factory: Callable[[], TelemetryCollector] = TelemetryCollector,
        start_background: bool = True,
    ) -> None:
        super().__init__()
        self.store = store
        self.settings = store.load()
        self._client_factory = client_factory
        self._snapshot: TelemetrySnapshot | None = None
        self._messages: list[dict[str, str]] = []
        self._pending_user = ""
        self._draft_response = ""
        self._chat_job: OllamaJob | None = None
        self._discovery_job: OllamaJob | None = None
        self._jobs: set[OllamaJob] = set()
        self._closing = False
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._monitor_thread: QThread | None = None
        self._monitor_worker: TelemetryWorker | None = None
        self._shutdown_timer = QTimer(self)
        self._shutdown_timer.setInterval(50)
        self._shutdown_timer.timeout.connect(self._check_shutdown)
        self.setWindowTitle("NEXUS AI · v0.3")
        self.resize(1160, 780)
        self.setMinimumSize(820, 560)
        self.setStyleSheet(_STYLE)
        self._build_ui()
        self._apply_policy()
        if store.warning:
            self.settings_status.setText(store.warning)
        if start_background:
            self._start_monitor(collector_factory)
            QTimer.singleShot(0, self.refresh_models)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)
        heading = QHBoxLayout()
        title = QLabel("NEXUS AI")
        title.setObjectName("title")
        heading.addWidget(title)
        subtitle = QLabel("v0.3  /  Local intelligence. Live telemetry.")
        subtitle.setObjectName("subtitle")
        heading.addWidget(subtitle)
        heading.addStretch()
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.open_settings)
        heading.addWidget(self.settings_button)
        root.addLayout(heading)

        profiles = QHBoxLayout()
        profiles.addWidget(QLabel("Performance profile"))
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(PROFILE_NAMES)
        self.profile_combo.setCurrentText(self.settings.profile)
        self.profile_combo.currentTextChanged.connect(self._profile_changed)
        profiles.addWidget(self.profile_combo)
        self.policy_label = QLabel()
        self.policy_label.setWordWrap(True)
        self.policy_label.setObjectName("muted")
        profiles.addWidget(self.policy_label, 1)
        root.addLayout(profiles)
        scope = QLabel(
            "Profiles tune inference requests and monitoring. Changes apply to the next reply."
        )
        scope.setObjectName("muted")
        root.addWidget(scope)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        chat = QWidget()
        chat_layout = QVBoxLayout(chat)
        chat_layout.setContentsMargins(0, 0, 8, 0)
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Ollama model"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(160)
        self.model_combo.currentIndexChanged.connect(self._model_changed)
        model_row.addWidget(self.model_combo, 1)
        self.refresh_button = QPushButton("Refresh models")
        self.refresh_button.clicked.connect(self.refresh_models)
        model_row.addWidget(self.refresh_button)
        chat_layout.addLayout(model_row)
        self.connection_status = QLabel("Connect to Ollama to discover installed models.")
        self.connection_status.setWordWrap(True)
        self.connection_status.setTextFormat(Qt.TextFormat.PlainText)
        chat_layout.addWidget(self.connection_status)
        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setPlaceholderText(
            "Your conversation stays in this session. Start with a message below."
        )
        self.transcript.document().setMaximumBlockCount(10000)
        self.transcript.setAccessibleName("Chat transcript")
        chat_layout.addWidget(self.transcript, 1)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText("Ask NEXUS…  (Ctrl+Enter to send)")
        self.prompt.setFixedHeight(100)
        self.prompt.setAccessibleName("Message")
        self.prompt.textChanged.connect(self._update_controls)
        chat_layout.addWidget(self.prompt)
        actions = QHBoxLayout()
        self.clear_button = QPushButton("Clear chat")
        self.clear_button.clicked.connect(self._clear_chat)
        actions.addWidget(self.clear_button)
        actions.addStretch()
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_generation)
        actions.addWidget(self.stop_button)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("primary")
        self.send_button.setEnabled(False)
        self.send_button.clicked.connect(self.send_message)
        actions.addWidget(self.send_button)
        chat_layout.addLayout(actions)
        self._send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self._send_shortcut.activated.connect(self.send_message)
        splitter.addWidget(chat)

        hardware = QWidget()
        hardware.setMinimumWidth(245)
        hardware_layout = QVBoxLayout(hardware)
        hardware_layout.setContentsMargins(8, 0, 0, 0)
        hardware_layout.addWidget(QLabel("LIVE HARDWARE"))
        self.cpu_card = MetricCard("CPU utilization")
        self.ram_card = MetricCard("System memory")
        hardware_layout.addWidget(self.cpu_card)
        hardware_layout.addWidget(self.ram_card)
        self.gpu_status = QLabel("Checking optional NVIDIA telemetry…")
        self.gpu_status.setWordWrap(True)
        self.gpu_status.setTextFormat(Qt.TextFormat.PlainText)
        hardware_layout.addWidget(self.gpu_status)
        gpu_scroll = QScrollArea()
        gpu_scroll.setWidgetResizable(True)
        self._gpu_container = QWidget()
        self._gpu_layout = QVBoxLayout(self._gpu_container)
        self._gpu_layout.setContentsMargins(0, 0, 0, 0)
        self._gpu_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        gpu_scroll.setWidget(self._gpu_container)
        self._gpu_cards: dict[int, MetricCard] = {}
        hardware_layout.addWidget(gpu_scroll, 1)
        splitter.addWidget(hardware)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)
        self.settings_status = QLabel()
        self.settings_status.setWordWrap(True)
        self.settings_status.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.settings_status)
        self.setCentralWidget(central)

    def _start_monitor(self, factory: Callable[[], TelemetryCollector]) -> None:
        self._monitor_thread = QThread(self)
        self._monitor_worker = TelemetryWorker(factory)
        self._monitor_worker.moveToThread(self._monitor_thread)
        self._monitor_thread.started.connect(self._monitor_worker.start)
        self._monitor_worker.sampled.connect(self._show_telemetry)
        self._monitor_worker.failed.connect(self._telemetry_failed)
        self.monitor_interval_changed.connect(self._monitor_worker.set_interval)
        self.monitor_stop_requested.connect(self._monitor_worker.stop)
        self._monitor_worker.finished.connect(self._monitor_thread.quit)
        self._monitor_thread.finished.connect(self._monitor_worker.deleteLater)
        self._monitor_thread.start()
        self._apply_policy()

    def _policy(self) -> InferencePolicy:
        snapshot = self._snapshot
        return resolve_policy(
            self.settings.profile,
            cpu_percent=(snapshot.cpu_percent or 0) if snapshot else 0,
            ram_available_bytes=snapshot.ram_available_bytes if snapshot else None,
        )

    def _apply_policy(self) -> None:
        policy = self._policy()
        self.policy_label.setText(policy.description)
        self.monitor_interval_changed.emit(policy.monitor_interval_ms)

    def _persist(self, candidate: Settings) -> bool:
        try:
            normalized = validate_settings(candidate)
            self.store.save(normalized)
        except (OSError, ValueError) as exc:
            self.settings_status.setText(f"Settings were not saved: {exc}")
            return False
        self.settings = normalized
        self.settings_status.setText("")
        return True

    @Slot(str)
    def _profile_changed(self, profile: str) -> None:
        if not self._persist(replace(self.settings, profile=profile)):
            self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentText(self.settings.profile)
            self.profile_combo.blockSignals(False)
        self._apply_policy()

    @Slot(int)
    def _model_changed(self, index: int) -> None:
        model = self.model_combo.itemData(index)
        if model:
            self._persist(replace(self.settings, model=model))
        self._update_controls()

    @Slot()
    def open_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Ollama settings")
        dialog.setMinimumWidth(440)
        layout = QFormLayout(dialog)
        url = QLineEdit(self.settings.ollama_url)
        url.setAccessibleName("Ollama server URL")
        layout.addRow("Server URL", url)
        hint = QLabel("Use an existing Ollama server, such as http://127.0.0.1:11434.")
        hint.setWordWrap(True)
        layout.addRow(hint)
        error = QLabel()
        error.setWordWrap(True)
        error.setTextFormat(Qt.TextFormat.PlainText)
        layout.addRow(error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )

        def save() -> None:
            candidate = replace(self.settings, ollama_url=url.text())
            if self._persist(candidate):
                dialog.accept()
                self._clear_chat()
                self.refresh_models()
            else:
                error.setText(self.settings_status.text())

        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        dialog.exec()

    def _start_job(self, job: OllamaJob) -> None:
        self._jobs.add(job)
        job.signals.result.connect(self._job_result)
        job.signals.failed.connect(self._job_failed)
        job.signals.chunk.connect(self._chat_chunk)
        job.signals.finished.connect(self._job_finished)
        self._pool.start(job)
        self._update_controls()

    @Slot()
    def refresh_models(self) -> None:
        if self._closing or self._chat_job is not None or self._discovery_job is not None:
            return
        self.connection_status.setText("Connecting to Ollama…")
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.blockSignals(False)
        job = OllamaJob("models", self.settings.ollama_url, self._client_factory)
        self._discovery_job = job
        self._start_job(job)

    @Slot()
    def send_message(self) -> None:
        prompt = self.prompt.toPlainText().strip()
        model = self.model_combo.currentData()
        if self._closing or self._chat_job or self._discovery_job or not prompt or not model:
            return
        self._persist(replace(self.settings, model=model))
        # Keep context bounded; larger context windows still depend on the selected model.
        messages = self._messages[-40:] + [{"role": "user", "content": prompt}]
        self._pending_user = prompt
        self._draft_response = ""
        self.transcript.appendPlainText(f"You\n{prompt}\n\nNEXUS · {model}\n")
        self.prompt.clear()
        self.connection_status.setText("Generating…")
        job = OllamaJob(
            "chat",
            self.settings.ollama_url,
            self._client_factory,
            model=model,
            messages=messages,
            policy=self._policy(),
        )
        self._chat_job = job
        self._start_job(job)

    @Slot(object, str)
    def _chat_chunk(self, job: OllamaJob, text: str) -> None:
        if job is not self._chat_job or self._closing or job.cancel_event.is_set():
            return
        self._draft_response += text
        cursor = self.transcript.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.transcript.setTextCursor(cursor)
        self.transcript.ensureCursorVisible()

    @Slot(object, object)
    def _job_result(self, job: OllamaJob, result: object) -> None:
        if self._closing:
            return
        if job is self._discovery_job:
            models = result
            self.model_combo.blockSignals(True)
            for model in models:
                self.model_combo.addItem(model.name, model.name)
            selected = self.model_combo.findData(self.settings.model)
            if selected >= 0:
                self.model_combo.setCurrentIndex(selected)
            self.model_combo.blockSignals(False)
            if models:
                self.connection_status.setText(
                    f"Ollama connected · {len(models)} installed model(s)"
                )
            else:
                self.connection_status.setText(
                    "No installed models. Run 'ollama pull llama3.2:3b', then refresh models."
                )
        elif job is self._chat_job:
            if job.cancel_event.is_set():
                self.transcript.appendPlainText(
                    "\n[Generation stopped; partial reply excluded from context.]\n"
                )
                self.connection_status.setText("Stopped. Ready for another message.")
            elif self._draft_response:
                self._messages.extend(
                    [
                        {"role": "user", "content": self._pending_user},
                        {"role": "assistant", "content": self._draft_response},
                    ]
                )
                self._messages = self._messages[-40:]
                self.transcript.appendPlainText("\n")
                self.connection_status.setText("Ready · reply complete")
            else:
                self.transcript.appendPlainText("[Ollama completed without answer text.]\n")
                self.connection_status.setText(
                    "No answer text returned. Try another model or prompt."
                )

    @Slot(object, str)
    def _job_failed(self, job: OllamaJob, error: str) -> None:
        if self._closing:
            return
        self.connection_status.setText(error)
        if job is self._chat_job:
            self.transcript.appendPlainText(f"\n[Reply failed: {error}]\n")
            if not self.prompt.toPlainText():
                self.prompt.setPlainText(self._pending_user)

    @Slot(object)
    def _job_finished(self, job: OllamaJob) -> None:
        self._jobs.discard(job)
        if job is self._chat_job:
            self._chat_job = None
            self._pending_user = ""
        if job is self._discovery_job:
            self._discovery_job = None
        self._update_controls()

    @Slot()
    def stop_generation(self) -> None:
        if self._chat_job is not None:
            self._chat_job.cancel_event.set()
            self.stop_button.setEnabled(False)
            self.connection_status.setText(
                "Stopping… waiting for the next response chunk or network timeout."
            )

    @Slot()
    def _clear_chat(self) -> None:
        if self._chat_job is None:
            self._messages.clear()
            self.transcript.clear()

    @Slot()
    def _update_controls(self) -> None:
        busy = bool(self._jobs) or self._closing
        self.send_button.setEnabled(
            not busy
            and bool(self.prompt.toPlainText().strip())
            and bool(self.model_combo.currentData())
        )
        self.refresh_button.setEnabled(not busy)
        self.model_combo.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.clear_button.setEnabled(not busy)
        self.profile_combo.setEnabled(not self._closing)
        self.prompt.setEnabled(not self._closing)
        self.stop_button.setEnabled(
            self._chat_job is not None
            and not self._chat_job.cancel_event.is_set()
            and not self._closing
        )

    @Slot(object)
    def _show_telemetry(self, snapshot: TelemetrySnapshot) -> None:
        self._snapshot = snapshot
        cpu = snapshot.cpu_percent
        cpu_text = f"{cpu:.1f}%" if cpu is not None else snapshot.cpu_status
        self.cpu_card.update_metric(cpu, cpu_text)
        ram = snapshot.ram_percent
        ram_text = (
            f"{ram:.1f}%  ·  {_gib(snapshot.ram_used_bytes)} / {_gib(snapshot.ram_total_bytes)}"
            if ram is not None
            else snapshot.ram_status
        )
        self.ram_card.update_metric(ram, ram_text)
        self.gpu_status.setText(snapshot.gpu_status)
        indices = {gpu.index for gpu in snapshot.gpus}
        for index in list(self._gpu_cards):
            if index not in indices:
                self._gpu_cards.pop(index).deleteLater()
        for gpu in snapshot.gpus:
            if gpu.index not in self._gpu_cards:
                card = MetricCard(f"GPU {gpu.index} · {gpu.name}")
                self._gpu_cards[gpu.index] = card
                self._gpu_layout.addWidget(card)
            utilization = (
                f"{gpu.utilization_percent:.0f}% utilization"
                if gpu.utilization_percent is not None
                else "Utilization unavailable"
            )
            temperature = (
                f"{gpu.temperature_c:.0f} °C"
                if gpu.temperature_c is not None
                else "Temperature unavailable"
            )
            detail = (
                f"{utilization}\nVRAM: {_gib(gpu.memory_used_bytes)} / "
                f"{_gib(gpu.memory_total_bytes)}\n{temperature}"
            )
            self._gpu_cards[gpu.index].update_metric(gpu.utilization_percent, detail)
        self._apply_policy()

    @Slot(str)
    def _telemetry_failed(self, error: str) -> None:
        self._snapshot = None
        self.cpu_card.update_metric(None, "CPU telemetry unavailable")
        self.ram_card.update_metric(None, "RAM telemetry unavailable")
        for card in self._gpu_cards.values():
            card.deleteLater()
        self._gpu_cards.clear()
        self.gpu_status.setText(f"Telemetry unavailable: {error}")
        self._apply_policy()

    def closeEvent(self, event: QCloseEvent) -> None:
        monitor_running = self._monitor_thread is not None and self._monitor_thread.isRunning()
        if self._jobs or self._pool.activeThreadCount() or monitor_running:
            event.ignore()
            if not self._closing:
                self._closing = True
                for job in self._jobs:
                    job.cancel_event.set()
                if monitor_running:
                    self.monitor_stop_requested.emit()
                self.connection_status.setText("Closing… waiting for background work to finish.")
                self._update_controls()
                self._shutdown_timer.start()
            return
        self._shutdown_timer.stop()
        event.accept()

    @Slot()
    def _check_shutdown(self) -> None:
        monitor_running = self._monitor_thread is not None and self._monitor_thread.isRunning()
        if not self._jobs and not self._pool.activeThreadCount() and not monitor_running:
            self._shutdown_timer.stop()
            self.close()
