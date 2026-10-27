"""Connect v1 services to the existing localized desktop without changing routes."""

from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from nexus_ai import __version__
from nexus_ai.i18n import Text
from nexus_ai.ui.conversation_panel import ConversationPanel
from nexus_ai.ui.diagnostics_panels import (
    GamepadPanel,
    HardwarePanel,
    StoragePanel,
    UpdatePanel,
)
from nexus_ai.ui.game_center import GameCenter
from nexus_ai.ui.remote_panel import RemotePanel
from nexus_ai.voice import VoiceFoundation, parse_voice_intent


class V1Features:
    def _install_v1_panels(self):
        self._effective_profile = self.settings.profile
        self.game_center = GameCenter(
            self.i18n,
            self.store.path,
            base_mode=self.settings.profile,
            base_url=self.settings.ollama_url,
            client_factory=self._client_factory,
        )
        self.game_center.effective_profile.connect(self._effective_mode_changed)
        self.game_center.network_busy_changed.connect(self._update_controls)
        self.storage_panel = StoragePanel(self.i18n)
        self.hardware_panel = HardwarePanel(self.i18n)
        self.gamepad_panel = GamepadPanel(self.i18n)
        self.update_panel = UpdatePanel(
            self.i18n, __version__, self.store.path.parent / "verified-updates"
        )
        for route, panel in (
            ("gaming", self.game_center),
            ("ssd", self.storage_panel),
            ("rgb", self.hardware_panel),
            ("gamepad", self.gamepad_panel),
            ("updates", self.update_panel),
        ):
            # Keep the existing title/description and honest disabled device writes.
            self.module_pages[route].layout().insertWidget(3, panel)
        self.conversations = ConversationPanel(
            self.i18n, self.store.path.with_name("conversations.sqlite3")
        )
        self.conversations.loaded.connect(self._load_conversation)
        self.conversations.cleared.connect(lambda: self._load_conversation([]))
        self.conversations.busy_changed.connect(self._update_controls)
        self.pages["assistant"].layout().insertWidget(2, self.conversations)
        self.access_dialog = QDialog(self)
        self.i18n.bind(self.access_dialog, Text("Voice and remote access"), "setWindowTitle")
        self.access_dialog.resize(640, 650)
        access_layout = QVBoxLayout(self.access_dialog)
        self.remote_panel = RemotePanel(self.i18n, self._remote_status, self._approved_command)
        access_layout.addWidget(self.remote_panel)
        self.voice = VoiceFoundation()
        voice_status = QLabel()
        voice_status.setWordWrap(True)
        self.i18n.bind(voice_status, self.voice.status().reason)
        access_layout.addWidget(voice_status)
        microphone = QPushButton()
        self.i18n.bind(microphone, Text("Microphone and speech · unavailable"))
        microphone.setEnabled(False)
        access_layout.addWidget(microphone)
        command_row = QHBoxLayout()
        self.command_input = QLineEdit()
        self.i18n.bind(
            self.command_input,
            Text("Text command, e.g. статус or игровой режим"),
            "setPlaceholderText",
        )
        command_row.addWidget(self.command_input, 1)
        command_button = QPushButton()
        self.i18n.bind(command_button, Text("Run approved text command"))
        command_button.clicked.connect(self._run_text_command)
        self.command_input.returnPressed.connect(self._run_text_command)
        command_row.addWidget(command_button)
        access_layout.addLayout(command_row)
        self.command_status = QLabel()
        self.command_status.setWordWrap(True)
        access_layout.addWidget(self.command_status)
        self.access_button = QPushButton()
        self.i18n.bind(self.access_button, Text("Voice and remote access"))
        self.access_button.clicked.connect(self.access_dialog.show)
        self.pages["assistant"].layout().insertWidget(3, self.access_button)
        self._v1_panels = (
            self.game_center,
            self.conversations,
            self.storage_panel,
            self.hardware_panel,
            self.gamepad_panel,
            self.update_panel,
            self.remote_panel,
        )

    def _start_v1(self):
        self.game_center.start()
        self.conversations.refresh()

    def _stop_v1(self):
        self.access_dialog.hide()
        for panel in self._v1_panels:
            panel.shutdown()

    def _v1_busy(self):
        return any(panel.busy for panel in self._v1_panels)

    @Slot(str)
    def _effective_mode_changed(self, mode):
        self._effective_profile = mode
        blocked = self.profile_combo.blockSignals(True)
        self.profile_combo.setCurrentIndex(self.profile_combo.findData(mode))
        self.profile_combo.blockSignals(blocked)
        self._apply_policy()

    @Slot(object)
    def _load_conversation(self, messages):
        if self._closing or self._chat_job is not None:
            return
        self._messages = [dict(message) for message in messages][-40:]
        self._transcript_segments.clear()
        self.transcript.clear()
        for message in messages:
            # Persisted content is user/model data, never interpreted as markup or translated.
            author = Text("You") if message["role"] == "user" else "NEXUS"
            self._append_transcript(
                Text("{author}\n{content}\n", author=author, content=message["content"])
            )

    def _remote_status(self):
        snapshot = self._snapshot
        return {
            "profile": self._effective_profile,
            "language": self.settings.language,
            "generating": self._chat_job is not None,
            "cpu_percent": snapshot.cpu_percent if snapshot else None,
            "ram_percent": snapshot.ram_percent if snapshot else None,
        }

    def _approved_command(self, command, params=None):
        if self._closing:
            raise ValueError(Text("The application is closing."))
        params = params or {}
        if command == "status":
            return self._remote_status()
        if command == "stop_generation":
            self.stop_generation()
            return {"stopped": True}
        if command == "set_profile":
            profile = params.get("profile")
            index = self.profile_combo.findData(profile)
            if index < 0:
                raise ValueError(Text("Choose a supported performance profile."))
            # Explicitly save the base mode even when the effective mode already matches it.
            if self.profile_combo.currentIndex() == index:
                self._profile_changed(profile)
            else:
                self.profile_combo.setCurrentIndex(index)
            return {"profile": self._effective_profile}
        raise ValueError(Text("This command is not allowed."))

    @Slot()
    def _run_text_command(self):
        intent = parse_voice_intent(self.command_input.text(), self.settings.language)
        if intent is None:
            self.i18n.bind(self.command_status, Text("This command is not allowed."))
            return
        result = self._approved_command(
            intent.command, {"profile": intent.profile} if intent.profile else {}
        )
        if intent.command == "status":
            message = Text("Current profile: {profile}", profile=Text(result["profile"]))
        else:
            message = Text("Approved command completed.")
        self.i18n.bind(self.command_status, message)
