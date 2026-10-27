"""Opt-in Game Guard UI. All filesystem, process and HTTP work runs in a pool."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Event

from PySide6.QtCore import QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from nexus_ai.gaming import (
    GameConfiguration,
    GameDetection,
    GameProfile,
    GameProfileStore,
    ProcessDetector,
    validate_configuration,
)
from nexus_ai.i18n import Text, error_text
from nexus_ai.lifecycle import LifecycleController, LifecycleDecision
from nexus_ai.ollama import OllamaClient
from nexus_ai.ui.dashboard import ResponsiveGrid
from nexus_ai.ui.localization import Translator
from nexus_ai.workers import JobSignals


class _Task(QRunnable):
    def __init__(self, kind, action):
        super().__init__()
        self.kind = kind
        self.action = action
        self.cancel_event = Event()
        self.signals = JobSignals()

    @Slot()
    def run(self):
        try:
            if not self.cancel_event.is_set():
                self.signals.result.emit(self, self.action())
        except Exception as exc:
            self.signals.failed.emit(self, error_text(exc))
        finally:
            self.signals.finished.emit(self)


class GameCenter(QWidget):
    """Embed in the existing Gaming page; no service starts until ``start``.

    ``busy`` describes queued/running I/O (also used during window shutdown).
    ``network_busy`` alone blocks chat and endpoint changes, not a process scan.
    Only successful chat/load completion may call ``note_model_used``.
    """

    effective_profile = Signal(str)
    busy_changed = Signal(bool)
    network_busy_changed = Signal(bool)

    def __init__(
        self,
        i18n: Translator,
        settings_path: Path,
        *,
        base_mode="Smart",
        base_url="http://127.0.0.1:11434",
        client_factory=OllamaClient,
        detector=None,
        parent=None,
    ):
        super().__init__(parent)
        self.i18n = i18n
        self.store = GameProfileStore(Path(settings_path).with_name("games.json"))
        self.controller = LifecycleController(base_mode)
        self.config = GameConfiguration()
        self.base_url = base_url
        self.client_factory = client_factory
        self.detector = detector if detector is not None else ProcessDetector()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._tasks = set()
        self._network_busy = False
        self._closing = False
        self._loaded = False
        self._last_mode = base_mode
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self.poll)
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.enable = QCheckBox()
        i18n.bind(self.enable, Text("Enable automatic game detection"))
        layout.addWidget(self.enable)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        i18n.bind(
            self.warning,
            Text(
                "Only configured executable names are detected. No processes are stopped. "
                "Ollama model residency is shared: unloading a NEXUS-used model can affect "
                "other clients using that same model."
            ),
        )
        layout.addWidget(self.warning)
        self.games = QListWidget()
        self.games.setMaximumHeight(150)
        layout.addWidget(self.games)
        self.name_input = QLineEdit()
        i18n.bind(self.name_input, Text("Game name"), "setPlaceholderText")
        layout.addWidget(self.name_input)
        self.executables_input = QLineEdit()
        i18n.bind(
            self.executables_input,
            Text("Executable names separated by semicolons, e.g. game.exe; launcher.exe"),
            "setPlaceholderText",
        )
        layout.addWidget(self.executables_input)
        self.allow_unload = QCheckBox()
        unload_caption = QLabel()
        unload_caption.setWordWrap(True)
        unload_caption.setBuddy(self.allow_unload)
        consent = Text("Allow unloading models used by NEXUS for this game")
        i18n.bind(unload_caption, consent)
        i18n.bind(self.allow_unload, consent, "setAccessibleName")
        unload_row = QHBoxLayout()
        unload_row.addWidget(self.allow_unload)
        unload_row.addWidget(unload_caption, 1)
        self.allow_unload.setChecked(False)
        layout.addLayout(unload_row)
        self.add_button = QPushButton()
        i18n.bind(self.add_button, Text("Add game"))
        self.remove_button = QPushButton()
        i18n.bind(self.remove_button, Text("Remove selected game"))
        self.update_button = QPushButton()
        i18n.bind(self.update_button, Text("Update selected game"))
        self.restore_button = QPushButton()
        i18n.bind(self.restore_button, Text("Restore NEXUS model on demand"))
        self.actions = ResponsiveGrid(
            [self.add_button, self.update_button, self.remove_button, self.restore_button],
            wide_columns=4,
            breakpoint=900,
            narrow_columns=2,
        )
        layout.addWidget(self.actions)
        self.status = QLabel()
        self.status.setWordWrap(True)
        i18n.bind(self.status, Text("Automatic game detection is disabled."))
        layout.addWidget(self.status)
        self.add_button.clicked.connect(self.add_game)
        self.remove_button.clicked.connect(self.remove_game)
        self.update_button.clicked.connect(self.update_game)
        self.restore_button.clicked.connect(self.restore_model)
        self.enable.toggled.connect(self._toggle)
        self.games.currentRowChanged.connect(self._selection_changed)
        self._update_controls()

    @property
    def busy(self):
        return bool(self._tasks) or bool(self._pool.activeThreadCount())

    @property
    def network_busy(self):
        return self._network_busy

    def start(self):
        if not self._loaded and not self._tasks and not self._closing:
            self._submit("load", self.store.load)

    def _submit(self, kind, action):
        if self._closing:
            return
        task = _Task(kind, action)
        task.signals.result.connect(self._result)
        task.signals.failed.connect(self._failed)
        task.signals.finished.connect(self._finished)
        self._tasks.add(task)
        if kind in {"unload", "restore"}:
            self._network_busy = True
            self.network_busy_changed.emit(True)
        self.busy_changed.emit(True)
        self._update_controls()
        self._pool.start(task)

    def _save(self, config):
        normalized = validate_configuration(config)

        def save():
            self.store.save(normalized)
            return normalized

        self._submit("save", save)

    @Slot()
    def add_game(self):
        if not self._loaded or self.busy or self._closing:
            return
        profile = GameProfile(
            self.name_input.text(),
            tuple(part.strip() for part in self.executables_input.text().split(";")),
            "Gaming",
            self.allow_unload.isChecked(),
        )
        try:
            self._save(replace(self.config, profiles=(*self.config.profiles, profile)))
        except ValueError as exc:
            self.i18n.bind(self.status, error_text(exc))

    @Slot()
    def remove_game(self):
        row = self.games.currentRow()
        if self.busy or self._closing or not 0 <= row < len(self.config.profiles):
            return
        self._save(
            replace(
                self.config, profiles=self.config.profiles[:row] + self.config.profiles[row + 1 :]
            )
        )

    @Slot()
    def update_game(self):
        row = self.games.currentRow()
        if self.busy or self._closing or not 0 <= row < len(self.config.profiles):
            return
        profile = replace(
            self.config.profiles[row],
            name=self.name_input.text(),
            executables=tuple(part.strip() for part in self.executables_input.text().split(";")),
            unload_model=self.allow_unload.isChecked(),
        )
        profiles = list(self.config.profiles)
        profiles[row] = profile
        try:
            self._save(replace(self.config, profiles=tuple(profiles)))
        except ValueError as exc:
            self.i18n.bind(self.status, error_text(exc))

    @Slot(int)
    def _selection_changed(self, row):
        if 0 <= row < len(self.config.profiles):
            profile = self.config.profiles[row]
            self.name_input.setText(profile.name)
            self.executables_input.setText("; ".join(profile.executables))
            self.allow_unload.setChecked(profile.unload_model)
        self._update_controls()

    @Slot(bool)
    def _toggle(self, checked):
        if not self._loaded or self.busy or self._closing:
            return
        self._save(replace(self.config, enabled=checked))

    def poll(self):
        if self._loaded and self.config.enabled and not self.busy and not self._closing:
            config = self.config
            self._submit("scan", lambda: self.detector.scan(config))

    def _apply(self, decision: LifecycleDecision, *, force_profile=False):
        self.i18n.bind(self.status, decision.status)
        if decision.mode != self._last_mode or force_profile:
            self._last_mode = decision.mode
            self.effective_profile.emit(decision.mode)
        if decision.unload_model is not None:
            self._model_operation("unload", decision.unload_model)

    def set_base_mode(self, mode):
        # A user can select a new base profile during a game; keep the combo on
        # the effective game policy while remembering their requested exit mode.
        self._apply(self.controller.set_base_mode(mode), force_profile=True)

    def set_chat_busy(self, busy):
        self._apply(self.controller.set_busy(busy))
        self._update_controls()

    def note_model_used(self, model):
        self.controller.note_model_used(model)
        self._update_controls()

    def request_restore(self):
        """Call before an explicit chat request; the chat itself loads on demand."""
        return self.controller.request_restore()

    def set_endpoint(self, base_url):
        if self.network_busy:
            raise RuntimeError(Text("Wait for the model operation before changing the server."))
        if base_url != self.base_url:
            mode, busy = self.controller.base_mode, self.controller.busy
            self.base_url = base_url
            self.controller = LifecycleController(mode)
            self.controller.set_busy(busy)
            self._apply(self.controller.observe(GameDetection(None, (), True, "")))
            self._update_controls()

    @Slot()
    def restore_model(self):
        model = self.controller.owned_model
        if not model or self.busy or self.controller.busy or self._closing:
            return
        self.controller.request_restore()
        self._model_operation("restore", model)

    def _model_operation(self, kind, model):
        if self._closing:
            self.controller.unload_failed(model)
            return
        url, factory = self.base_url, self.client_factory

        def operate():
            with factory(url) as client:
                if kind == "unload":
                    client.unload_model(model)
                else:
                    client.load_model(model)
            return model

        self._submit(kind, operate)

    @Slot(object, object)
    def _result(self, task, result):
        if self._closing:
            return
        if task.kind in {"load", "save"}:
            self.config = result
            self._loaded = True
            self.enable.blockSignals(True)
            self.enable.setChecked(result.enabled)
            self.enable.blockSignals(False)
            self.games.clear()
            for profile in result.profiles:
                self.games.addItem(f"{profile.name}: {'; '.join(profile.executables)}")
            if task.kind == "save":
                self.name_input.clear()
                self.executables_input.clear()
                self.allow_unload.setChecked(False)
            if result.enabled:
                self._timer.start()
            else:
                self._timer.stop()
            if not result.enabled or self.controller.active not in result.profiles:
                self._apply(self.controller.observe(GameDetection(None, (), True, "")))
            if self.store.warning:
                self.i18n.bind(self.status, self.store.warning)
            QTimer.singleShot(0, self.poll)
        elif task.kind == "scan":
            self._apply(self.controller.observe(result))
        elif task.kind == "unload":
            self.controller.unloaded(result)
            self.i18n.bind(self.status, Text("NEXUS model unloaded. Restore it when needed."))
        elif task.kind == "restore":
            self.controller.note_model_used(result)
            self.i18n.bind(self.status, Text("NEXUS model restored on demand."))

    @Slot(object, object)
    def _failed(self, task, message):
        if task.kind == "unload":
            model = self.controller.pending_operation
            if model:
                self.controller.unload_failed(model)
        if not self._closing:
            self.enable.blockSignals(True)
            self.enable.setChecked(self.config.enabled)
            self.enable.blockSignals(False)
            self.i18n.bind(self.status, Text("Game Guard error: {detail}", detail=message))

    @Slot(object)
    def _finished(self, task):
        self._tasks.discard(task)
        if task.kind in {"unload", "restore"}:
            self._network_busy = False
            self.network_busy_changed.emit(False)
        self._update_controls()
        self.busy_changed.emit(bool(self._tasks))

    def _update_controls(self, *_):
        editable = self._loaded and not self._tasks and not self._closing
        for widget in (self.enable, self.name_input, self.executables_input, self.allow_unload):
            widget.setEnabled(editable)
        self.add_button.setEnabled(editable)
        self.remove_button.setEnabled(editable and self.games.currentRow() >= 0)
        self.update_button.setEnabled(editable and self.games.currentRow() >= 0)
        self.restore_button.setEnabled(
            editable and not self.controller.busy and self.controller.owned_model is not None
        )

    def shutdown(self):
        self._closing = True
        self._timer.stop()
        for task in self._tasks:
            task.cancel_event.set()
        self._update_controls()
