"""Desktop chat and live hardware dashboard."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace

from PySide6.QtCore import Qt, QThread, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from nexus_ai import __version__
from nexus_ai.history import TelemetryHistory
from nexus_ai.modules import MODULES, IntegrationRegistry
from nexus_ai.ollama import OllamaClient
from nexus_ai.profiles import PROFILE_NAMES, InferencePolicy, resolve_policy
from nexus_ai.settings import Settings, SettingsStore, validate_settings
from nexus_ai.telemetry import TelemetryCollector, TelemetrySnapshot
from nexus_ai.ui.dashboard import (
    COLORS,
    HistoryChart,
    ModulePage,
    ResponsiveGrid,
    SectionHeader,
    Sidebar,
    label,
    scroll_page,
)
from nexus_ai.ui.theme import STYLE
from nexus_ai.workers import OllamaJob, TelemetryWorker


def _gib(value: int | None) -> str:
    return "Unavailable" if value is None else f"{value / 1024**3:.1f} GiB"


class MetricCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(label(title, "eyebrow"))
        self.value = QLabel("Waiting for telemetry…")
        self.value.setWordWrap(True)
        self.value.setObjectName("metricValue")
        layout.addWidget(self.value)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.hide()
        layout.addWidget(self.bar)

    def update_metric(self, percent: float | None, detail: str) -> None:
        self.value.setTextFormat(Qt.TextFormat.PlainText)
        self.value.setText(detail)
        self.value.setStyleSheet("font-size: 13px;" if len(detail) > 40 else "")
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
        self._pending_chunks: list[str] = []
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(30)
        self._render_timer.timeout.connect(self._flush_chunks)
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
        self.setWindowTitle(f"NEXUS AI · v{__version__}")
        self.resize(1400, 940)
        self.setMinimumSize(720, 540)
        self.setStyleSheet(STYLE)
        self._build_ui()
        self._apply_policy()
        if store.warning:
            self.settings_status.setText(store.warning)
        if start_background:
            self._start_monitor(collector_factory)
            QTimer.singleShot(0, self.refresh_models)

    def _build_ui(self) -> None:
        self.history = TelemetryHistory()
        self.integrations = IntegrationRegistry()
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = Sidebar()
        root.addWidget(self.sidebar)
        workspace = QWidget()
        body = QVBoxLayout(workspace)
        body.setContentsMargins(24, 20, 24, 16)
        body.setSpacing(18)
        toolbar = QHBoxLayout()
        self.breadcrumb = label("WORKSPACE / OVERVIEW", "breadcrumb")
        toolbar.addWidget(self.breadcrumb, 1)
        toolbar.addWidget(label("PROFILE", "eyebrow"))
        self.profile_combo = QComboBox()
        self.profile_combo.setAccessibleName("Performance profile")
        self.profile_combo.addItems(PROFILE_NAMES)
        self.profile_combo.setCurrentText(self.settings.profile)
        self.profile_combo.currentTextChanged.connect(self._profile_changed)
        toolbar.addWidget(self.profile_combo)
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.open_settings)
        toolbar.addWidget(self.settings_button)
        body.addLayout(toolbar)
        self.policy_label = label("")
        self.policy_label.setToolTip("Profiles apply to the next Ollama request, not OS settings.")
        body.addWidget(self.policy_label)
        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {}
        self.module_pages: dict[str, ModulePage] = {}
        self._add_page("overview", "Overview", self._build_dashboard())
        self._add_page("assistant", "Assistant", self._build_assistant())
        for spec in MODULES:
            page = ModulePage(spec)
            if page.gaming_button is not None:
                page.gaming_button.clicked.connect(
                    lambda: self.profile_combo.setCurrentText("Gaming")
                )
            self.module_pages[spec.key] = page
            self._add_page(spec.key, spec.title, scroll_page(page))
        self.sidebar.finish()
        body.addWidget(self.stack, 1)
        self.settings_status = label("")
        body.addWidget(self.settings_status)
        root.addWidget(workspace, 1)
        self.setCentralWidget(central)
        self.navigate("overview")

    def _add_page(self, key: str, title: str, page: QWidget) -> None:
        self.pages[key] = page
        self.stack.addWidget(page)
        self.sidebar.add_route(key, title).clicked.connect(lambda: self.navigate(key))

    def navigate(self, key: str) -> None:
        if key not in self.pages:
            raise ValueError(f"Unknown workspace: {key}")
        self.stack.setCurrentWidget(self.pages[key])
        for name, button in self.sidebar.buttons.items():
            button.setChecked(name == key)
        self.breadcrumb.setText(f"WORKSPACE / {self.sidebar.buttons[key].text().upper()}")

    def _build_dashboard(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(16)
        layout.addWidget(
            SectionHeader("System overview", "Live host signals. No simulated metrics.")
        )
        self.cpu_card = MetricCard("CPU / UTILIZATION")
        self.ram_card = MetricCard("RAM / SYSTEM MEMORY")
        self.gpu_card = MetricCard("GPU / NVIDIA UTILIZATION")
        self.vram_card = MetricCard("VRAM / DEVICE MEMORY")
        self.metric_grid = ResponsiveGrid(
            [self.cpu_card, self.ram_card, self.gpu_card, self.vram_card],
            wide_columns=4,
            breakpoint=1000,
            narrow_columns=2,
        )
        layout.addWidget(self.metric_grid)
        self.history_status = label("History begins with this session · up to 300 samples / 10 min")
        layout.addWidget(self.history_status)
        self.charts = [
            HistoryChart("CPU utilization / %", self.history, "cpu", COLORS[0]),
            HistoryChart("Memory usage / %", self.history, "ram", COLORS[1]),
            HistoryChart("GPU utilization / % · all devices", self.history, "gpu:", COLORS[2]),
            HistoryChart("VRAM usage / % · all devices", self.history, "vram:", COLORS[3]),
            HistoryChart("Host temperatures / °C", self.history, "temperature:", COLORS[2]),
            HistoryChart("GPU temperatures / °C", self.history, "gpu_temp:", COLORS[0]),
        ]
        self.chart_grid = ResponsiveGrid(self.charts, wide_columns=2, breakpoint=720)
        layout.addWidget(self.chart_grid)
        thermal = QFrame()
        thermal.setObjectName("panel")
        thermal_layout = QVBoxLayout(thermal)
        thermal_layout.setContentsMargins(18, 16, 18, 16)
        thermal_layout.addWidget(label("TEMPERATURE SENSORS", "eyebrow"))
        self.temperature_status = label("Waiting for real sensor readings…")
        thermal_layout.addWidget(self.temperature_status)
        self.temperature_values = label("", "body")
        thermal_layout.addWidget(self.temperature_values)
        self.fan_button = QPushButton("Fan controls · no validated SDK")
        self.fan_button.setEnabled(False)
        thermal_layout.addWidget(self.fan_button)
        layout.addWidget(thermal)
        self.gpu_status = label("Checking optional NVIDIA telemetry…")
        layout.addWidget(self.gpu_status)
        self._gpu_container = QWidget()
        self._gpu_layout = QVBoxLayout(self._gpu_container)
        self._gpu_layout.setContentsMargins(0, 0, 0, 0)
        self._gpu_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._gpu_cards: dict[int, MetricCard] = {}
        layout.addWidget(self._gpu_container)
        layout.addStretch()
        return scroll_page(content)

    def _build_assistant(self) -> QWidget:
        chat = QWidget()
        chat_layout = QVBoxLayout(chat)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(14)
        chat_layout.addWidget(
            SectionHeader(
                "Your local assistant",
                "Streamed from your Ollama server. Your model, your workspace.",
            )
        )
        model_row = QHBoxLayout()
        model_row.addWidget(label("MODEL", "eyebrow"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(100)
        self.model_combo.setAccessibleName("Installed Ollama model")
        self.model_combo.currentIndexChanged.connect(self._model_changed)
        model_row.addWidget(self.model_combo, 1)
        self.refresh_button = QPushButton("Refresh models")
        self.refresh_button.clicked.connect(self.refresh_models)
        model_row.addWidget(self.refresh_button)
        chat_layout.addLayout(model_row)
        self.connection_status = label("Connect to Ollama to discover installed models.")
        chat_layout.addWidget(self.connection_status)
        self.transcript = QPlainTextEdit()
        self.transcript.setObjectName("transcript")
        self.transcript.setReadOnly(True)
        self.transcript.setPlaceholderText(
            "A clear space to think.\n\nChoose an installed model, then start a conversation.\n"
            "History stays in this session; prompts go to your configured Ollama server."
        )
        self.transcript.document().setMaximumBlockCount(10000)
        self.transcript.setAccessibleName("Chat transcript")
        chat_layout.addWidget(self.transcript, 1)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText("Ask NEXUS…  (Ctrl+Enter to send)")
        self.prompt.setFixedHeight(90)
        self.prompt.setAccessibleName("Message")
        self.prompt.textChanged.connect(self._update_controls)
        chat_layout.addWidget(self.prompt)
        actions = QHBoxLayout()
        self.clear_button = QPushButton("Clear chat")
        self.clear_button.clicked.connect(self._clear_chat)
        actions.addWidget(self.clear_button)
        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(
            lambda: QApplication.clipboard().setText(self.transcript.toPlainText())
        )
        actions.addWidget(self.copy_button)
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
        self._stop_shortcut = QShortcut(QKeySequence("Escape"), self)
        self._stop_shortcut.activated.connect(self.stop_generation)
        return chat

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "sidebar"):
            self.sidebar.setFixedWidth(166 if self.width() < 980 else 208)

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
        self.navigate("assistant")
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
        self._pending_chunks.append(text)
        if not self._render_timer.isActive():
            self._render_timer.start()

    @Slot()
    def _flush_chunks(self) -> None:
        self._render_timer.stop()
        text = "".join(self._pending_chunks)
        self._pending_chunks.clear()
        if not text or self._closing:
            return
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
                self.model_combo.setItemData(
                    self.model_combo.count() - 1,
                    f"{model.name} · {_gib(model.size_bytes)} download size",
                    Qt.ItemDataRole.ToolTipRole,
                )
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
            self._flush_chunks()
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
            self._flush_chunks()
            self.transcript.appendPlainText(f"\n[Reply failed: {error}]\n")
            if not self.prompt.toPlainText():
                self.prompt.setPlainText(self._pending_user)

    @Slot(object)
    def _job_finished(self, job: OllamaJob) -> None:
        self._jobs.discard(job)
        if job is self._chat_job:
            self._flush_chunks()
            self._chat_job = None
            self._pending_user = ""
        if job is self._discovery_job:
            self._discovery_job = None
        self._update_controls()

    @Slot()
    def stop_generation(self) -> None:
        if self._chat_job is not None:
            self._flush_chunks()
            self._chat_job.cancel()
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
        self.copy_button.setEnabled(not self._closing)
        for button in self.sidebar.buttons.values():
            button.setEnabled(not self._closing)
        self.module_pages["gaming"].gaming_button.setEnabled(not self._closing)
        self.stop_button.setEnabled(
            self._chat_job is not None
            and not self._chat_job.cancel_event.is_set()
            and not self._closing
        )

    @Slot(object)
    def _show_telemetry(self, snapshot: TelemetrySnapshot) -> None:
        if self._closing:
            return
        self._snapshot = snapshot
        self.history.append(snapshot)
        for chart in self.charts:
            keys = self.history.keys(chart.prefix)
            chart.setToolTip("\n".join(keys) or "No sensor readings available")
            chart.setAccessibleDescription("Historical series: " + ", ".join(keys))
            chart.update()
        self.history_status.setText(
            f"{len(self.history.points)} real samples · up to 300 samples / 10 min · "
            "GPU lines follow device index"
        )
        gpu = snapshot.gpus[0] if snapshot.gpus else None
        self.gpu_card.update_metric(
            gpu.utilization_percent if gpu else None,
            (
                f"{gpu.utilization_percent:.1f}% · {gpu.name}"
                if gpu and gpu.utilization_percent is not None
                else "GPU unavailable"
            ),
        )
        vram = (
            100 * gpu.memory_used_bytes / gpu.memory_total_bytes
            if gpu and gpu.memory_used_bytes is not None and gpu.memory_total_bytes
            else None
        )
        self.vram_card.update_metric(
            vram,
            f"{_gib(gpu.memory_used_bytes)} / {_gib(gpu.memory_total_bytes)}"
            if gpu
            else "VRAM unavailable",
        )
        self.gpu_card.setToolTip("First reported GPU; all devices are shown below and in charts.")
        self.vram_card.setToolTip("Memory of first reported GPU; all devices are charted.")
        self.temperature_status.setText(snapshot.temperature_status)
        self.temperature_values.setText(
            "\n".join(
                f"{sensor.name}: {sensor.current_c:.1f} °C" for sensor in snapshot.temperatures
            )
            or "No host sensor data. Windows CPU temperatures require a supported sensor provider."
        )
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
        self.history.append_values(time.monotonic(), {})
        for chart in self.charts:
            chart.update()
        self.temperature_status.setText("Temperature readings unavailable")
        self.temperature_values.setText("")
        self.gpu_card.update_metric(None, "GPU unavailable")
        self.vram_card.update_metric(None, "VRAM unavailable")
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
                self._render_timer.stop()
                self._pending_chunks.clear()
                for job in self._jobs:
                    job.cancel()
                if monitor_running:
                    self.monitor_stop_requested.emit()
                message = "Closing… waiting for background work to finish."
                self.connection_status.setText(message)
                self.settings_status.setText(message + " Network reads can take up to 60 seconds.")
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
