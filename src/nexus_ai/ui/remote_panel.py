"""Explicit remote listener controls; all sockets and TLS setup stay in workers."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from nexus_ai.i18n import Text
from nexus_ai.remote import RemoteCommandQueue, RemoteConfig, RemoteServer, generate_token
from nexus_ai.ui.background import TaskRunner


class RemotePanel(QWidget):
    busy_changed = Signal(bool)

    def __init__(self, i18n, status_handler, command_handler, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self.status_handler = status_handler
        self.command_handler = command_handler
        self.runner = TaskRunner(self)
        self.runner.failed.connect(self._error)
        self.runner.busy_changed.connect(self._busy_changed)
        self._resources = {}  # Accessed only by this serial runner's operations.
        self._queue = None
        self._running = False
        self._closing = False
        self.origin = None
        layout = QVBoxLayout(self)
        notice = QLabel()
        notice.setWordWrap(True)
        i18n.bind(
            notice,
            Text(
                "Remote control is off by default. LAN access requires your own trusted TLS "
                "certificate. Approved commands: status, stop generation and change profile."
            ),
        )
        layout.addWidget(notice)
        form = QFormLayout()
        self.host = QLineEdit("127.0.0.1")
        self.port = QSpinBox()
        self.port.setRange(0, 65535)
        self.certfile = QLineEdit()
        self.keyfile = QLineEdit()
        self.token = QLineEdit()
        self.token.setReadOnly(True)
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        for widget, text in (
            (self.host, Text("Local bind address")),
            (self.port, Text("Port (0 selects an available port)")),
            (self.certfile, Text("TLS certificate file")),
            (self.keyfile, Text("TLS private key file")),
            (self.token, Text("Pairing token")),
        ):
            label = QLabel()
            i18n.bind(label, text)
            form.addRow(label, widget)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.start_button = QPushButton()
        self.stop_button = QPushButton()
        self.reveal_button = QPushButton()
        self.reveal_button.setCheckable(True)
        for widget, text, action in (
            (self.start_button, Text("Start remote control"), self.start),
            (self.stop_button, Text("Stop remote control"), self.stop),
            (self.reveal_button, Text("Show pairing token"), self._reveal),
        ):
            i18n.bind(widget, text)
            widget.clicked.connect(action)
            row.addWidget(widget)
        layout.addLayout(row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        i18n.bind(self.status, Text("Remote control is stopped."))
        layout.addWidget(self.status)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._drain)
        self._update_controls()

    @property
    def busy(self):
        return self.runner.busy

    @property
    def running(self):
        return self._running

    def _reveal(self, reveal):
        self.token.setEchoMode(QLineEdit.EchoMode.Normal if reveal else QLineEdit.EchoMode.Password)

    def _error(self, message):
        self.i18n.bind(self.status, message)
        if not self._running:
            self.token.clear()
            self.timer.stop()
            if self._queue is not None:
                self._queue.close()

    def _busy_changed(self, busy):
        self._update_controls()
        self.busy_changed.emit(busy)

    def _update_controls(self):
        idle = not self.runner.pending and not self._closing
        self.start_button.setEnabled(idle and not self._running)
        self.stop_button.setEnabled(idle and self._running)
        self.reveal_button.setEnabled(self._running and not self._closing)
        for widget in (self.host, self.port, self.certfile, self.keyfile):
            widget.setEnabled(idle and not self._running)

    def start(self):
        if self._closing or self._running or self.runner.pending:
            return
        config = RemoteConfig(
            enabled=True,
            host=self.host.text().strip(),
            port=self.port.value(),
            certfile=self.certfile.text().strip() or None,
            keyfile=self.keyfile.text().strip() or None,
        )
        token = generate_token()
        queue = RemoteCommandQueue()
        self._queue = queue
        self.token.setText(token)
        self.reveal_button.setChecked(False)
        self._reveal(False)
        self.timer.start()

        def start():
            server = RemoteServer(config, token, queue.submit)
            origin = server.start()
            self._resources["server"] = server
            return origin

        def started(origin):
            self.origin = origin
            self._running = True
            if not self._closing:
                self.i18n.bind(
                    self.status,
                    Text("Remote control is listening at {address}.", address=origin),
                )

        self.runner.submit(start, started)

    def _drain(self):
        if self._queue is not None and not self._closing:
            self._queue.drain(self._dispatch)

    def _dispatch(self, command, params):
        if command == "status":
            return self.status_handler()
        return self.command_handler(command, params)

    def _stop_worker(self):
        server = self._resources.pop("server", None)
        if server is not None:
            server.stop()

    def _stopped(self, _):
        self._running = False
        self.origin = None
        self.token.clear()
        self.reveal_button.setChecked(False)
        self._reveal(False)
        self.i18n.bind(self.status, Text("Remote control is stopped."))

    def stop(self):
        if self._closing or self.runner.pending or not self._running:
            return
        self.timer.stop()
        if self._queue is not None:
            self._queue.close()
        self.runner.submit(self._stop_worker, self._stopped)

    def shutdown(self):
        if self._closing:
            return
        self._closing = True
        self.timer.stop()
        if self._queue is not None:
            self._queue.close()
        # Serial order also closes a listener whose start is still in flight.
        if self._running or self.runner.pending:
            self.runner.submit(self._stop_worker, self._stopped)
        self.runner.shutdown()
        self._update_controls()
