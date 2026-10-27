"""Desktop chat and live hardware dashboard."""

from __future__ import annotations

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
from nexus_ai.i18n import JoinedText, Text, error_text
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
from nexus_ai.ui.localization import Translator
from nexus_ai.ui.theme import STYLE
from nexus_ai.ui.v1 import V1Features
from nexus_ai.workers import OllamaJob, TelemetryWorker


def _gib(value: int | None) -> str:
    return Text("Unavailable") if value is None else Text("{value:.1f} GiB", value=value / 1024**3)


class MetricCard(QFrame):
    def __init__(self, title: str, i18n: Translator) -> None:
        super().__init__()
        self.i18n = i18n
        self.setObjectName("panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        heading = label("")
        self.i18n.bind(heading, title)
        layout.addWidget(heading)
        self.value = QLabel("Waiting for telemetry…")
        self.value.setWordWrap(True)
        self.value.setObjectName("metricValue")
        layout.addWidget(self.value)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.hide()
        layout.addWidget(self.bar)
        self.i18n.watch_tree(self)

    def update_metric(self, percent: float | None, detail: str) -> None:
        self.value.setTextFormat(Qt.TextFormat.PlainText)
        self.i18n.bind(self.value, detail, "setText")
        self.value.setStyleSheet("font-size: 13px;" if len(detail) > 40 else "")
        self.bar.setVisible(percent is not None)
        if percent is not None:
            self.bar.setValue(round(percent))


class MainWindow(V1Features, QMainWindow):
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
        self.i18n = Translator(self.settings.language, self)
        self._transcript_segments: list[tuple[bool, str]] = []
        self._available_models = []
        self._sensor_display_names = {}
        self._last_settings_error = ""
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
        self._install_v1_panels()
        self.i18n.watch_tree(self)
        self.i18n.language_changed.connect(self._retranslate_view)
        self._retranslate_view()
        self._apply_policy()
        if store.warning:
            self.i18n.bind(self.settings_status, store.warning, "setText")
        if start_background:
            self._start_v1()
            self._start_monitor(collector_factory)
            QTimer.singleShot(0, self.refresh_models)

    def _build_ui(self) -> None:
        self.history = TelemetryHistory()
        self.integrations = IntegrationRegistry()
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = Sidebar(self.i18n)
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
        self.i18n.bind(self.profile_combo, "Performance profile", "setAccessibleName")
        for profile in PROFILE_NAMES:
            self.profile_combo.addItem(profile, profile)
        self.profile_combo.setCurrentIndex(self.profile_combo.findData(self.settings.profile))
        self.profile_combo.currentTextChanged.connect(self._profile_changed)
        toolbar.addWidget(self.profile_combo)
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.open_settings)
        toolbar.addWidget(self.settings_button)
        body.addLayout(toolbar)
        self.policy_label = label("")
        self.i18n.bind(
            self.policy_label,
            "Profiles apply to the next Ollama request, not OS settings.",
            "setToolTip",
        )
        body.addWidget(self.policy_label)
        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {}
        self._route_titles: dict[str, str] = {}
        self.module_pages: dict[str, ModulePage] = {}
        self._add_page("overview", "Overview", self._build_dashboard())
        self._add_page("assistant", "Assistant", self._build_assistant())
        for spec in MODULES:
            page = ModulePage(spec, self.i18n)
            if page.gaming_button is not None:
                page.gaming_button.clicked.connect(
                    lambda: self.profile_combo.setCurrentIndex(
                        self.profile_combo.findData("Gaming")
                    )
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
        self._route_titles[key] = title
        self.stack.addWidget(page)
        self.sidebar.add_route(key, title).clicked.connect(lambda: self.navigate(key))

    def navigate(self, key: str) -> None:
        if key not in self.pages:
            raise ValueError(f"Unknown workspace: {key}")
        self.stack.setCurrentWidget(self.pages[key])
        for name, button in self.sidebar.buttons.items():
            button.setChecked(name == key)
        self.i18n.bind(
            self.breadcrumb,
            Text("WORKSPACE / {page}", page=Text(self._route_titles[key])),
            "setText",
        )

    def _build_dashboard(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(16)
        layout.addWidget(
            SectionHeader("System overview", "Live host signals. No simulated metrics.")
        )
        self.cpu_card = MetricCard("CPU / UTILIZATION", self.i18n)
        self.ram_card = MetricCard("RAM / SYSTEM MEMORY", self.i18n)
        self.gpu_card = MetricCard("GPU / NVIDIA UTILIZATION", self.i18n)
        self.vram_card = MetricCard("VRAM / DEVICE MEMORY", self.i18n)
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
            HistoryChart("CPU utilization / %", self.history, "cpu", COLORS[0], self.i18n),
            HistoryChart("Memory usage / %", self.history, "ram", COLORS[1], self.i18n),
            HistoryChart(
                "GPU utilization / % · all devices", self.history, "gpu:", COLORS[2], self.i18n
            ),
            HistoryChart(
                "VRAM usage / % · all devices", self.history, "vram:", COLORS[3], self.i18n
            ),
            HistoryChart(
                "Host temperatures / °C", self.history, "temperature:", COLORS[2], self.i18n
            ),
            HistoryChart("GPU temperatures / °C", self.history, "gpu_temp:", COLORS[0], self.i18n),
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
        self.i18n.bind(self.model_combo, "Installed Ollama model", "setAccessibleName")
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
        self.i18n.bind(
            self.transcript,
            "A clear space to think.\n\nChoose an installed model, then start a conversation.\n"
            "Completed turns are saved locally; prompts go to your configured Ollama server.",
            "setPlaceholderText",
        )
        self.transcript.document().setMaximumBlockCount(10000)
        self.i18n.bind(self.transcript, "Chat transcript", "setAccessibleName")
        chat_layout.addWidget(self.transcript, 1)
        self.prompt = QPlainTextEdit()
        self.i18n.bind(self.prompt, "Ask NEXUS…  (Ctrl+Enter to send)", "setPlaceholderText")
        self.prompt.setFixedHeight(90)
        self.i18n.bind(self.prompt, "Message", "setAccessibleName")
        self.prompt.textChanged.connect(self._update_controls)
        chat_layout.addWidget(self.prompt)
        actions = QHBoxLayout()
        self.clear_button = QPushButton("Clear chat")
        self.clear_button.clicked.connect(self._clear_chat)
        actions.addWidget(self.clear_button)
        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(
            lambda: self.i18n.bind(
                QApplication.clipboard(), self.transcript.toPlainText(), "setText"
            )
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
            self._resize_sidebar()

    def _resize_sidebar(self) -> None:
        compact = 192 if self.i18n.language == "ru" else 166
        self.sidebar.setFixedWidth(compact if self.width() < 980 else 208)

    def set_language(self, language: str) -> bool:
        if self._closing:
            return False
        if language == self.settings.language:
            return True
        if not self._persist(replace(self.settings, language=language)):
            return False
        self.i18n.set_language(language)
        return True

    def _retranslate_view(self) -> None:
        self._resize_sidebar()
        blocked = self.profile_combo.blockSignals(True)
        for index in range(self.profile_combo.count()):
            self.profile_combo.setItemText(
                index, self.i18n.text(self.profile_combo.itemData(index))
            )
        self.profile_combo.blockSignals(blocked)
        self._apply_policy()
        current = self.stack.currentWidget()
        for key, page in self.pages.items():
            if page is current:
                self.navigate(key)
                break
        for index, model in enumerate(self._available_models):
            if index < self.model_combo.count():
                self.model_combo.setItemData(
                    index,
                    self.i18n.text(
                        Text(
                            "{model} · {size} download size",
                            model=model.name,
                            size=_gib(model.size_bytes),
                        )
                    ),
                    Qt.ItemDataRole.ToolTipRole,
                )
        self._flush_chunks()
        scrollbar = self.transcript.verticalScrollBar()
        at_end = scrollbar.value() == scrollbar.maximum()
        position = scrollbar.value()
        self.transcript.setPlainText(
            "".join(
                self.i18n.text(message) if localized else message
                for localized, message in self._transcript_segments
            )
        )
        scrollbar.setValue(scrollbar.maximum() if at_end else position)

    def _record_segment(self, message: str, localized: bool) -> None:
        if not localized and self._transcript_segments and not self._transcript_segments[-1][0]:
            message = self._transcript_segments.pop()[1] + message
        if not localized:
            message = message[-500_000:]
        self._transcript_segments.append((localized, message))
        while len(self._transcript_segments) > 1 and (
            len(self._transcript_segments) > 1000
            or sum(len(part) for _, part in self._transcript_segments) > 500_000
        ):
            self._transcript_segments.pop(0)

    def _append_transcript(self, message: str) -> None:
        if self.transcript.toPlainText():
            self._record_segment("\n", False)
        self._record_segment(message, True)
        self.transcript.appendPlainText(self.i18n.text(message))

    def _start_monitor(self, factory: Callable[[], TelemetryCollector]) -> None:
        self._monitor_thread = QThread(self)
        self._monitor_worker = TelemetryWorker(factory)
        self._monitor_worker.moveToThread(self._monitor_thread)
        self._monitor_thread.started.connect(self._monitor_worker.start)
        self._monitor_worker.sampled.connect(self._show_telemetry)
        self._monitor_worker.failed_at.connect(self._telemetry_failed)
        self.monitor_interval_changed.connect(self._monitor_worker.set_interval)
        self.monitor_stop_requested.connect(self._monitor_worker.stop)
        self._monitor_worker.finished.connect(self._monitor_thread.quit)
        self._monitor_thread.finished.connect(self._monitor_worker.deleteLater)
        self._monitor_thread.start()
        self._apply_policy()

    def _policy(self) -> InferencePolicy:
        snapshot = self._snapshot
        return resolve_policy(
            getattr(self, "_effective_profile", self.settings.profile),
            cpu_percent=(snapshot.cpu_percent or 0) if snapshot else 0,
            ram_available_bytes=snapshot.ram_available_bytes if snapshot else None,
        )

    def _apply_policy(self) -> None:
        policy = self._policy()
        self.i18n.bind(self.policy_label, policy.description, "setText")
        self.monitor_interval_changed.emit(policy.monitor_interval_ms)

    def _persist(self, candidate: Settings) -> bool:
        try:
            normalized = validate_settings(candidate)
            self.store.save(normalized)
        except (OSError, ValueError) as exc:
            self._last_settings_error = Text(
                "Settings were not saved: {error}", error=error_text(exc)
            )
            self.i18n.bind(self.settings_status, self._last_settings_error)
            return False
        self.settings = normalized
        self.i18n.bind(self.settings_status, "", "setText")
        return True

    @Slot(str)
    def _profile_changed(self, profile: str) -> None:
        profile = self.profile_combo.currentData()
        if not self._persist(replace(self.settings, profile=profile)):
            self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentIndex(self.profile_combo.findData(self.settings.profile))
            self.profile_combo.blockSignals(False)
        self.game_center.set_base_mode(self.settings.profile)
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
        dialog.setObjectName("settingsDialog")
        dialog.setWindowTitle("Settings")
        dialog.setMinimumWidth(440)
        layout = QFormLayout(dialog)
        language = QComboBox()
        language.setObjectName("languageCombo")
        language.addItem("Русский", "ru")
        language.addItem("English", "en")
        language.setCurrentIndex(language.findData(self.settings.language))
        layout.addRow("Language", language)
        note = label("Language changes are saved immediately. Other settings use Save.")
        layout.addRow(note)
        url = QLineEdit(self.settings.ollama_url)
        url.setObjectName("serverUrl")
        url.setAccessibleName("Ollama server URL")
        url.setEnabled(
            not self._jobs and not self.game_center.network_busy and not self.conversations.busy
        )
        layout.addRow("Server URL", url)
        hint = label("Use an existing Ollama server, such as http://127.0.0.1:11434.")
        layout.addRow(hint)
        error = label("")
        error.setObjectName("settingsError")
        layout.addRow(error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.i18n.bind(buttons.button(QDialogButtonBox.StandardButton.Save), "Save")
        self.i18n.bind(buttons.button(QDialogButtonBox.StandardButton.Cancel), "Cancel")

        def switch_language() -> None:
            if self.set_language(language.currentData()):
                self.i18n.bind(error, "")
            else:
                language.blockSignals(True)
                language.setCurrentIndex(language.findData(self.settings.language))
                language.blockSignals(False)
                self.i18n.bind(error, self._last_settings_error)

        language.currentIndexChanged.connect(switch_language)

        def save() -> None:
            if (
                self._jobs or self.game_center.network_busy or self.conversations.busy
            ) and url.text() != self.settings.ollama_url:
                self.i18n.bind(
                    error, "Wait for the current request before changing the server URL."
                )
                return
            previous_url = self.settings.ollama_url
            if self._persist(replace(self.settings, ollama_url=url.text())):
                dialog.accept()
                if self.settings.ollama_url != previous_url and not self._jobs:
                    self.game_center.set_endpoint(self.settings.ollama_url)
                    self._clear_chat()
                    self.refresh_models()
            else:
                self.i18n.bind(error, self._last_settings_error)

        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        self.i18n.watch_tree(dialog)
        dialog.exec()
        dialog.deleteLater()

    def _start_job(self, job: OllamaJob) -> None:
        self._jobs.add(job)
        self.game_center.set_chat_busy(True)
        self.conversations.set_chat_busy(True)
        job.signals.result.connect(self._job_result)
        job.signals.failed.connect(self._job_failed)
        job.signals.chunk.connect(self._chat_chunk)
        job.signals.finished.connect(self._job_finished)
        self._pool.start(job)
        self._update_controls()

    @Slot()
    def refresh_models(self) -> None:
        if (
            self._closing
            or self._chat_job is not None
            or self._discovery_job is not None
            or self.game_center.network_busy
        ):
            return
        self.i18n.bind(self.connection_status, "Connecting to Ollama…", "setText")
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
        if (
            self._closing
            or self._chat_job
            or self._discovery_job
            or not prompt
            or not model
            or self.game_center.network_busy
            or self.conversations.context_busy
        ):
            return
        self.game_center.request_restore()
        self.navigate("assistant")
        self._persist(replace(self.settings, model=model))
        # Keep context bounded; larger context windows still depend on the selected model.
        messages = self._messages[-40:] + [{"role": "user", "content": prompt}]
        self._pending_user = prompt
        self._draft_response = ""
        self._append_transcript(
            Text("You\n{prompt}\n\nNEXUS · {model}\n", prompt=prompt, model=model)
        )
        self.prompt.clear()
        self.i18n.bind(self.connection_status, "Generating…", "setText")
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
        self._record_segment(text, False)

    @Slot(object, object)
    def _job_result(self, job: OllamaJob, result: object) -> None:
        if self._closing:
            return
        if job is self._discovery_job:
            models = result
            self._available_models = models
            self.model_combo.blockSignals(True)
            for model in models:
                self.model_combo.addItem(model.name, model.name)
                self.model_combo.setItemData(
                    self.model_combo.count() - 1,
                    self.i18n.text(
                        Text(
                            "{model} · {size} download size",
                            model=model.name,
                            size=_gib(model.size_bytes),
                        )
                    ),
                    Qt.ItemDataRole.ToolTipRole,
                )
            selected = self.model_combo.findData(self.settings.model)
            if selected >= 0:
                self.model_combo.setCurrentIndex(selected)
            self.model_combo.blockSignals(False)
            if models:
                self.i18n.bind(
                    self.connection_status,
                    Text("Ollama connected · {count} installed model(s)", count=len(models)),
                    "setText",
                )
            else:
                self.i18n.bind(
                    self.connection_status,
                    "No installed models. Run 'ollama pull llama3.2:3b', then refresh models.",
                    "setText",
                )
        elif job is self._chat_job:
            self._flush_chunks()
            if job.cancel_event.is_set():
                self._append_transcript(
                    "\n[Generation stopped; partial reply excluded from context.]\n"
                )
                self.i18n.bind(
                    self.connection_status, "Stopped. Ready for another message.", "setText"
                )
            elif self._draft_response:
                if job.model:
                    self.game_center.note_model_used(job.model)
                    self.conversations.save_turn(self._pending_user, self._draft_response)
                self._messages.extend(
                    [
                        {"role": "user", "content": self._pending_user},
                        {"role": "assistant", "content": self._draft_response},
                    ]
                )
                self._messages = self._messages[-40:]
                self._append_transcript("\n")
                self.i18n.bind(self.connection_status, "Ready · reply complete", "setText")
            else:
                self._append_transcript("[Ollama completed without answer text.]\n")
                self.i18n.bind(
                    self.connection_status,
                    "No answer text returned. Try another model or prompt.",
                    "setText",
                )

    @Slot(object, object)
    def _job_failed(self, job: OllamaJob, error: object) -> None:
        if self._closing:
            return
        error = error_text(error)
        status = (
            error
            if isinstance(error, (Text, JoinedText))
            else Text(
                "Ollama request failed: {error}",
                error=error,
            )
        )
        self.i18n.bind(self.connection_status, status, "setText")
        if job is self._chat_job:
            self._flush_chunks()
            self._append_transcript(Text("\n[Reply failed: {error}]\n", error=error))
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
        self.game_center.set_chat_busy(bool(self._jobs))
        self.conversations.set_chat_busy(bool(self._jobs))
        self._update_controls()

    @Slot()
    def stop_generation(self) -> None:
        if self._chat_job is not None:
            self._flush_chunks()
            self._chat_job.cancel()
            self.stop_button.setEnabled(False)
            self.i18n.bind(
                self.connection_status,
                "Stopping… waiting for the next response chunk or network timeout.",
                "setText",
            )

    @Slot()
    def _clear_chat(self) -> None:
        if self._chat_job is None and not self.conversations.context_busy:
            self.conversations.new_conversation()

    @Slot()
    def _update_controls(self) -> None:
        busy = bool(self._jobs) or self._closing
        if hasattr(self, "game_center"):
            busy = busy or self.game_center.network_busy or self.conversations.context_busy
        self.send_button.setEnabled(
            not busy
            and bool(self.prompt.toPlainText().strip())
            and bool(self.model_combo.currentData())
        )
        self.refresh_button.setEnabled(not busy)
        self.model_combo.setEnabled(not busy)
        self.settings_button.setEnabled(not self._closing)
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

    def _series_label(self, key: str) -> str:
        if key == "cpu":
            return Text("CPU utilization / %")
        if key == "ram":
            return Text("Memory usage / %")
        prefix, _, index = key.partition(":")
        if prefix == "temperature":
            return self._sensor_display_names.get(key, index)
        template = {
            "gpu": "GPU {index}",
            "vram": "VRAM {index}",
            "gpu_temp": "GPU {index} temperature",
        }.get(prefix)
        return Text(template, index=index) if template else key

    @Slot(object)
    def _show_telemetry(self, snapshot: TelemetrySnapshot) -> None:
        if self._closing:
            return
        self._snapshot = snapshot
        self.history.append(snapshot)
        self._sensor_display_names.update(
            {f"temperature:{sensor.name}": sensor.name for sensor in snapshot.temperatures}
        )
        active = set(self.history.keys("temperature:"))
        self._sensor_display_names = {
            key: value for key, value in self._sensor_display_names.items() if key in active
        }
        for chart in self.charts:
            keys = self.history.keys(chart.prefix)
            self.i18n.bind(
                chart,
                JoinedText(self._series_label(key) for key in keys)
                or "No sensor readings available",
                "setToolTip",
            )
            self.i18n.bind(
                chart,
                Text(
                    "Historical series: {series}",
                    series=JoinedText((self._series_label(key) for key in keys), ", "),
                ),
                "setAccessibleDescription",
            )
            chart.update()
        self.i18n.bind(
            self.history_status,
            Text(
                "{count} real samples · up to 300 samples / 10 min · GPU lines follow device index",
                count=len(self.history.points),
            ),
            "setText",
        )
        gpu = snapshot.gpus[0] if snapshot.gpus else None
        self.gpu_card.update_metric(
            gpu.utilization_percent if gpu else None,
            (
                Text("{value:.1f}% · {name}", value=gpu.utilization_percent, name=gpu.name)
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
            Text(
                "{used} / {total}",
                used=_gib(gpu.memory_used_bytes),
                total=_gib(gpu.memory_total_bytes),
            )
            if gpu
            else "VRAM unavailable",
        )
        self.i18n.bind(
            self.gpu_card,
            "First reported GPU; all devices are shown below and in charts.",
            "setToolTip",
        )
        self.i18n.bind(
            self.vram_card, "Memory of first reported GPU; all devices are charted.", "setToolTip"
        )
        self.i18n.bind(self.temperature_status, snapshot.temperature_status, "setText")
        self.i18n.bind(
            self.temperature_values,
            JoinedText(
                Text("{name}: {value:.1f} °C", name=sensor.name, value=sensor.current_c)
                for sensor in snapshot.temperatures
            )
            or "No host sensor data. Windows CPU temperatures require a supported sensor provider.",
            "setText",
        )
        cpu = snapshot.cpu_percent
        cpu_text = Text("{value:.1f}%", value=cpu) if cpu is not None else snapshot.cpu_status
        self.cpu_card.update_metric(cpu, cpu_text)
        ram = snapshot.ram_percent
        ram_text = (
            Text(
                "{value:.1f}%  ·  {used} / {total}",
                value=ram,
                used=_gib(snapshot.ram_used_bytes),
                total=_gib(snapshot.ram_total_bytes),
            )
            if ram is not None
            else snapshot.ram_status
        )
        self.ram_card.update_metric(ram, ram_text)
        self.i18n.bind(self.gpu_status, snapshot.gpu_status, "setText")
        indices = {gpu.index for gpu in snapshot.gpus}
        for index in list(self._gpu_cards):
            if index not in indices:
                self._gpu_cards.pop(index).deleteLater()
        for gpu in snapshot.gpus:
            if gpu.index not in self._gpu_cards:
                card = MetricCard(
                    Text("GPU {index} · {name}", index=gpu.index, name=gpu.name), self.i18n
                )
                self._gpu_cards[gpu.index] = card
                self._gpu_layout.addWidget(card)
            utilization = (
                Text("{value:.0f}% utilization", value=gpu.utilization_percent)
                if gpu.utilization_percent is not None
                else "Utilization unavailable"
            )
            temperature = (
                Text("{value:.0f} °C", value=gpu.temperature_c)
                if gpu.temperature_c is not None
                else "Temperature unavailable"
            )
            detail = Text(
                "{utilization}\nVRAM: {used} / {total}\n{temperature}",
                utilization=Text(utilization) if type(utilization) is str else utilization,
                used=_gib(gpu.memory_used_bytes),
                total=_gib(gpu.memory_total_bytes),
                temperature=Text(temperature) if type(temperature) is str else temperature,
            )
            self._gpu_cards[gpu.index].update_metric(gpu.utilization_percent, detail)
        self._apply_policy()

    @Slot(str)
    @Slot(object, float)
    def _telemetry_failed(self, error: object, timestamp: float | None = None) -> None:
        # Worker timestamps retain emission order even when delivery to the UI
        # is delayed. Untimestamped callers insert a gap at the last known sample.
        if timestamp is not None:
            self.history.append_values(timestamp, {})
        elif self.history.points:
            self.history.append_values(self.history.points[-1].timestamp, {})
        for chart in self.charts:
            chart.update()
        self.i18n.bind(self.temperature_status, "Temperature readings unavailable", "setText")
        self.i18n.bind(self.temperature_values, "", "setText")
        self.gpu_card.update_metric(None, "GPU unavailable")
        self.vram_card.update_metric(None, "VRAM unavailable")
        self._snapshot = None
        self.cpu_card.update_metric(None, "CPU telemetry unavailable")
        self.ram_card.update_metric(None, "RAM telemetry unavailable")
        for card in self._gpu_cards.values():
            card.deleteLater()
        self._gpu_cards.clear()
        self.i18n.bind(
            self.gpu_status,
            Text("Telemetry unavailable: {error}", error=error_text(error)),
            "setText",
        )
        self._apply_policy()

    def closeEvent(self, event: QCloseEvent) -> None:
        monitor_running = self._monitor_thread is not None and self._monitor_thread.isRunning()
        if not self._closing:
            self._stop_v1()
        if self._jobs or self._pool.activeThreadCount() or monitor_running or self._v1_busy():
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
                self.i18n.bind(self.connection_status, message, "setText")
                self.i18n.bind(
                    self.settings_status,
                    Text(
                        "{message} Network reads can take up to 60 seconds.", message=Text(message)
                    ),
                    "setText",
                )
                self._update_controls()
                self._shutdown_timer.start()
            return
        self._shutdown_timer.stop()
        event.accept()

    @Slot()
    def _check_shutdown(self) -> None:
        monitor_running = self._monitor_thread is not None and self._monitor_thread.isRunning()
        if (
            not self._jobs
            and not self._pool.activeThreadCount()
            and not monitor_running
            and not self._v1_busy()
        ):
            self._shutdown_timer.stop()
            self.close()
