"""Worker-backed, read-only diagnostics and explicitly approved update downloads."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from nexus_ai.gamepad import GamepadDiagnostics
from nexus_ai.hardware import HardwareInventory
from nexus_ai.i18n import JoinedText, Text, error_text
from nexus_ai.storage import StorageDiagnostics
from nexus_ai.ui.dashboard import ResponsiveGrid
from nexus_ai.updates import DownloadApproval, ReleaseChecker


class _Signals(QObject):
    result = Signal(object)
    failed = Signal(object)
    finished = Signal()


class _Job(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.cancel_event = Event()
        self.signals = _Signals()

    def run(self):
        try:
            if not self.cancel_event.is_set():
                result = self.operation(self.cancel_event)
                if not self.cancel_event.is_set():
                    self.signals.result.emit(result)
        except Exception as exc:
            if not self.cancel_event.is_set():
                self.signals.failed.emit(error_text(exc))
        finally:
            self.signals.finished.emit()


class _Panel(QWidget):
    idle = Signal()

    def __init__(self, i18n, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._job = None
        self._closing = False
        self.layout_box = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(180)
        self.layout_box.addWidget(self.status)
        self.layout_box.addWidget(self.output)
        self.actions = QHBoxLayout()
        self.scan_button = QPushButton()
        self.i18n.bind(self.scan_button, Text("Run read-only diagnostics"))
        self.actions.addWidget(self.scan_button)
        self.layout_box.addLayout(self.actions)
        self.i18n.bind(self.status, Text("Not checked. Run a read-only check when ready."))

    @property
    def busy(self):
        return self._job is not None or self._pool.activeThreadCount() > 0

    def _submit(self, operation):
        if self.busy or self._closing:
            return
        self._job = _Job(operation)
        self._job.signals.result.connect(self._result)
        self._job.signals.failed.connect(self._failed)
        self._job.signals.finished.connect(self._finished)
        self.scan_button.setEnabled(False)
        self.i18n.bind(self.status, Text("Checking in the background…"))
        self._pool.start(self._job)

    @Slot(object)
    def _failed(self, message):
        self.i18n.bind(self.status, Text("Check failed: {error}", error=message))

    @Slot()
    def _finished(self):
        self._job = None
        self.scan_button.setEnabled(not self._closing)
        self.idle.emit()

    def shutdown(self):
        self._closing = True
        self.scan_button.setEnabled(False)
        if self._job is not None:
            self._job.cancel_event.set()

    def _show(self, report, lines):
        self.i18n.bind(self.status, report.message)
        self.i18n.bind(self.output, JoinedText(tuple(lines), "\n"), "setPlainText")


def _known(value):
    if value is None or value == "":
        return Text("Unavailable")
    return value


class StoragePanel(_Panel):
    def __init__(self, i18n, parent=None, *, collector_factory=StorageDiagnostics):
        super().__init__(i18n, parent)
        self._collector_factory = collector_factory
        self.scan_button.clicked.connect(self.scan)

    def scan(self):
        factory = self._collector_factory
        self._submit(lambda cancel: factory().collect())

    @Slot(object)
    def _result(self, report):
        lines = [
            Text("Windows Storage reliability counters; unavailable fields are not estimates.")
        ]
        for disk in report.disks:
            lines.extend(
                [
                    Text(
                        "Disk: {name} ({kind}, {bus})",
                        name=disk.name,
                        kind=disk.media_type,
                        bus=disk.bus_type,
                    ),
                    Text(
                        "Provider health: {health}; operations: {operations}",
                        health=_known(disk.health_status),
                        operations=", ".join(disk.operational_status),
                    ),
                    Text("Temperature: {value} °C", value=_known(disk.temperature_c)),
                    Text(
                        "Consumed wear: {value}% (not remaining health)",
                        value=_known(disk.wear_percent),
                    ),
                    Text("Power-on hours: {value}", value=_known(disk.power_on_hours)),
                    Text(
                        "Read errors: {read}; write errors: {write}",
                        read=_known(disk.read_errors_total),
                        write=_known(disk.write_errors_total),
                    ),
                    "",
                ]
            )
        self._show(report, lines)


class HardwarePanel(_Panel):
    def __init__(self, i18n, parent=None, *, collector_factory=HardwareInventory):
        super().__init__(i18n, parent)
        self._collector_factory = collector_factory
        self.scan_button.clicked.connect(self.scan)

    def scan(self):
        factory = self._collector_factory
        self._submit(lambda cancel: factory().collect())

    @Slot(object)
    def _result(self, report):
        lines = [Text("Detected names are evidence only; RGB and fan controls remain disabled.")]
        for capability in report.capabilities:
            lines.extend(
                [
                    Text(
                        "{title}: {devices}",
                        title=capability.title,
                        devices=", ".join(capability.candidate_names)
                        or Text("No candidate detected"),
                    ),
                    capability.reason,
                    "",
                ]
            )
        self._show(report, lines)


class GamepadPanel(_Panel):
    def __init__(self, i18n, parent=None, *, collector_factory=GamepadDiagnostics):
        super().__init__(i18n, parent)
        self._collector_factory = collector_factory
        self.scan_button.clicked.connect(self.scan)
        self.i18n.bind(self.scan_button, Text("Read XInput state"))

    def scan(self):
        factory = self._collector_factory
        self._submit(lambda cancel: factory().collect())

    @Slot(object)
    def _result(self, report):
        lines = [
            Text("Read-only XInput snapshot. Elite identity, paddles and rumble are not supported.")
        ]
        for controller in report.controllers:
            lines.extend(
                [
                    Text(
                        "Slot {slot}: buttons {buttons}",
                        slot=controller.slot,
                        buttons=f"0x{controller.buttons:04X}",
                    ),
                    Text(
                        "Triggers: left {left}, right {right}",
                        left=controller.left_trigger,
                        right=controller.right_trigger,
                    ),
                    Text(
                        "Sticks: left ({lx}, {ly}), right ({rx}, {ry})",
                        lx=controller.left_x,
                        ly=controller.left_y,
                        rx=controller.right_x,
                        ry=controller.right_y,
                    ),
                ]
            )
        self._show(report, lines)


class UpdatePanel(_Panel):
    def __init__(
        self, i18n, current_version, download_dir, parent=None, *, checker_factory=ReleaseChecker
    ):
        super().__init__(i18n, parent)
        self.current_version = current_version
        self.download_dir = Path(download_dir)
        self._checker_factory = checker_factory
        self._check = None
        self._downloading = False
        self.i18n.bind(self.scan_button, Text("Check GitHub Releases"))
        self.scan_button.clicked.connect(self.scan)
        self.assets = QComboBox()
        # Release filenames can be long. Their content must not determine the
        # minimum width of the dashboard or prevent compact reflow.
        self.assets.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.assets.setMinimumContentsLength(16)
        self.assets.setMinimumWidth(0)
        self.assets.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.download_button = QPushButton()
        self.i18n.bind(self.download_button, Text("Download and verify"))
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.download)
        self.cancel_button = QPushButton()
        self.i18n.bind(self.cancel_button, Text("Cancel download"))
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_download)
        self.install_button = QPushButton()
        self.i18n.bind(self.install_button, Text("Installation unavailable"))
        self.install_button.setEnabled(False)
        self.actions.removeWidget(self.scan_button)
        self.action_grid = ResponsiveGrid(
            [
                self.scan_button,
                self.assets,
                self.download_button,
                self.cancel_button,
                self.install_button,
            ],
            wide_columns=2,
            breakpoint=580,
            narrow_columns=1,
        )
        self.layout_box.addWidget(self.action_grid)

    def scan(self):
        factory, version = self._checker_factory, self.current_version

        def operation(cancel):
            with factory() as checker:
                return checker.check(version)

        self._check = None
        self.assets.clear()
        self.download_button.setEnabled(False)
        self._submit(operation)

    @Slot(object)
    def _result(self, result):
        if self._downloading:
            self.i18n.bind(
                self.status,
                Text(
                    "Verified download saved to {path}. Nothing was installed.",
                    path=str(result.path),
                ),
            )
            self.i18n.bind(
                self.output, Text("SHA256: {digest}", digest=result.sha256), "setPlainText"
            )
            return
        self._check = result
        lines = [Text("Only stable releases from misha2271/NEXUS-AI are checked.")]
        if result.release is not None:
            lines.append(result.release.page_url)
            for asset in result.release.assets:
                lines.append(
                    Text(
                        "{name}: {integrity}",
                        name=asset.name,
                        integrity=Text("SHA256 available")
                        if asset.verifiable
                        else Text("No verifiable SHA256; download disabled"),
                    )
                )
                if asset.verifiable and result.status == "available":
                    self.assets.addItem(asset.name, asset.name)
        lines.append(
            Text("SHA256 verifies integrity against GitHub metadata, not publisher identity.")
        )
        self._show(result, lines)
        self.download_button.setEnabled(self.assets.count() > 0 and not self._closing)

    def download(self):
        if self.busy or self._closing or self._check is None or self.assets.currentData() is None:
            return
        check, name = self._check, self.assets.currentData()
        yes = QMessageBox.StandardButton.Yes
        if (
            QMessageBox.question(
                self,
                self.i18n.text(Text("Approve download")),
                self.i18n.text(
                    Text("Download and verify {asset}? No installation will run.", asset=name)
                ),
                yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != yes
        ):
            return
        major_approved = False
        if check.major_update:
            major_approved = (
                QMessageBox.question(
                    self,
                    self.i18n.text(Text("Approve major update")),
                    self.i18n.text(
                        Text("This changes the major version. Explicitly approve this download?")
                    ),
                    yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                == yes
            )
            if not major_approved:
                return
        approval = DownloadApproval(check.release.tag, name, True, major_approved)
        factory, folder = self._checker_factory, self.download_dir

        def operation(cancel):
            with factory() as checker:
                return checker.stage_asset(check, name, folder, approval, cancel_event=cancel)

        self._downloading = True
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._submit(operation)

    def cancel_download(self):
        if self._job is not None:
            self._job.cancel_event.set()
            self.i18n.bind(self.status, Text("Update download cancellation requested."))

    @Slot()
    def _finished(self):
        self._downloading = False
        self.cancel_button.setEnabled(False)
        self.download_button.setEnabled(self.assets.count() > 0 and not self._closing)
        super()._finished()

    def shutdown(self):
        self.cancel_button.setEnabled(False)
        self.download_button.setEnabled(False)
        super().shutdown()
