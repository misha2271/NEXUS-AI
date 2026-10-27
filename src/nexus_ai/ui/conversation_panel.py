"""Explicit conversation selection and durable, serial completed-turn saves."""

from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nexus_ai.conversations import ConversationStore
from nexus_ai.i18n import Text
from nexus_ai.ui.background import TaskRunner
from nexus_ai.ui.dashboard import ResponsiveGrid


class ConversationPanel(QWidget):
    loaded = Signal(object)
    cleared = Signal()
    busy_changed = Signal(bool)

    def __init__(self, i18n, db_path, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self.store = ConversationStore(db_path)
        self.runner = TaskRunner(self)
        self.runner.failed.connect(self._error)
        self.runner.busy_changed.connect(self._busy_changed)
        self._session = uuid4().hex
        self._messages = []
        # Only serial database operations touch these records. A new chat uses
        # another key, so a pending old save cannot replace the new chat.
        self._records = {}
        self._identifier = None
        self._summaries = ()
        self._chat_busy = False
        self._context_pending = 0
        self._closing = False
        layout = QVBoxLayout(self)
        self.selector = QComboBox()
        self.selector.setMinimumWidth(140)
        self.selector.setMinimumContentsLength(12)
        self.selector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        layout.addWidget(self.selector)
        self.new_button = QPushButton()
        self.load_button = QPushButton()
        self.delete_button = QPushButton()
        self.refresh_button = QPushButton()
        for button, text, action in (
            (self.new_button, Text("New conversation"), self.new_conversation),
            (self.load_button, Text("Resume conversation"), self.load_selected),
            (self.delete_button, Text("Delete conversation"), self.delete_selected),
            (self.refresh_button, Text("Refresh conversations"), self.refresh),
        ):
            i18n.bind(button, text)
            button.clicked.connect(action)
        self.actions = ResponsiveGrid(
            [self.new_button, self.load_button, self.delete_button, self.refresh_button],
            wide_columns=4,
            breakpoint=680,
            narrow_columns=2,
        )
        layout.addWidget(self.actions)
        self.status = QLabel()
        self.status.setWordWrap(True)
        i18n.bind(self.status, Text("Completed conversations are saved locally on this computer."))
        layout.addWidget(self.status)
        i18n.language_changed.connect(
            lambda: self._listed(self._summaries, preferred=self.selector.currentData())
        )
        self._update_controls()

    @property
    def busy(self):
        return self.runner.busy

    @property
    def context_busy(self):
        """Only operations that replace/remove context must pause new generation.

        Completed-turn saves and list refreshes remain serialized in the worker,
        but the user may send a follow-up while they finish.
        """
        return self._context_pending > 0

    def _submit_context(self, operation, done):
        self._context_pending += 1

        def finished():
            self._context_pending -= 1

        if not self.runner.submit(operation, done, finished=finished):
            self._context_pending -= 1

    def _error(self, message):
        self.i18n.bind(self.status, message)

    def _busy_changed(self, busy):
        self._update_controls()
        self.busy_changed.emit(busy)

    def set_chat_busy(self, busy):
        self._chat_busy = bool(busy)
        self._update_controls()

    def _update_controls(self):
        enabled = not self._chat_busy and not self._closing and not self.runner.pending
        for widget in (
            self.selector,
            self.new_button,
            self.load_button,
            self.delete_button,
            self.refresh_button,
        ):
            widget.setEnabled(enabled)

    def new_conversation(self):
        if self._chat_busy or self._closing:
            return
        self._session = uuid4().hex
        self._identifier = None
        self._messages = []
        self.cleared.emit()
        self.i18n.bind(
            self.status, Text("New conversation. Completed turns will be saved locally.")
        )

    def refresh(self):
        if not self._closing:
            self.runner.submit(self.store.list_conversations, self._listed)

    def _listed(self, summaries, *, preferred=None):
        self._summaries = summaries
        selected = self.selector.currentData()
        self.selector.clear()
        for summary in summaries:
            title = summary.title or self.i18n.text(Text("Untitled conversation"))
            self.selector.addItem(title, summary.id)
        index = self.selector.findData(preferred or self._identifier or selected)
        if index >= 0:
            self.selector.setCurrentIndex(index)
        self._update_controls()

    def save_turn(self, user, assistant):
        """Queue exact completed text. Cancelled/failed generations must not call this."""
        if self._closing:
            return
        self._messages.extend(
            ({"role": "user", "content": user}, {"role": "assistant", "content": assistant})
        )
        messages = tuple(dict(message) for message in self._messages)
        session = self._session
        title = " ".join(user.split())[:80]

        def save():
            current = self._records.get(session)
            if current is None:
                current = self.store.create(title)
                self._records[session] = current
            result = self.store.save(current.id, messages, expected_revision=current.revision)
            self._records[session] = result
            return result, self.store.list_conversations()

        def saved(result):
            conversation, summaries = result
            if session == self._session:
                self._identifier = conversation.id
                self.i18n.bind(self.status, Text("Conversation saved locally."))
            self._listed(summaries)

        self.runner.submit(save, saved)

    def load_selected(self):
        identifier = self.selector.currentData()
        if not identifier or self._chat_busy or self._closing:
            return
        session = uuid4().hex

        def load():
            conversation = self.store.load(identifier)
            self._records[session] = conversation
            return conversation

        def loaded(conversation):
            self._session = session
            self._identifier = conversation.id
            self._messages = [dict(message) for message in conversation.messages]
            self.loaded.emit(tuple(dict(message) for message in self._messages))
            self.i18n.bind(self.status, Text("Conversation restored from local storage."))

        self._submit_context(load, loaded)

    def delete_selected(self, checked=False, *, confirm=True):
        identifier = self.selector.currentData()
        if not identifier or self._chat_busy or self._closing:
            return
        if (
            confirm
            and QMessageBox.question(
                self,
                self.i18n.text(Text("Delete conversation")),
                self.i18n.text(Text("Permanently delete this locally saved conversation?")),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        def deleted(result):
            if identifier == self._identifier:
                self.new_conversation()
            self._listed(result)
            self.i18n.bind(self.status, Text("Conversation deleted."))

        def remove():
            self.store.delete(identifier)
            for session in [
                key for key, conversation in self._records.items() if conversation.id == identifier
            ]:
                del self._records[session]
            return self.store.list_conversations()

        self._submit_context(remove, deleted)

    def shutdown(self):
        self._closing = True
        self.runner.shutdown()
        self._update_controls()
