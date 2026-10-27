"""Localization contracts and live Qt switching; no test-wide locale override."""

from __future__ import annotations

import ast
import copy
import json
import re
from dataclasses import replace
from pathlib import Path
from string import Formatter
from threading import Event

import httpx
import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QDialogButtonBox, QLabel, QLineEdit
from shiboken6 import isValid

from nexus_ai.i18n import JoinedText, Text, error_text, render
from nexus_ai.modules import MODULES
from nexus_ai.ollama import OllamaClient, OllamaError, OllamaModel
from nexus_ai.profiles import PROFILE_NAMES, resolve_policy
from nexus_ai.settings import Settings, SettingsStore, validate_settings
from nexus_ai.telemetry import GPUReading, TelemetrySnapshot, TemperatureReading
from nexus_ai.translations import RU
from nexus_ai.ui.window import MainWindow
from nexus_ai.workers import OllamaJob


@pytest.fixture
def windows(qtbot, tmp_path):
    instances = []
    releases = []

    def create(language="ru", client_factory=OllamaClient):
        store = SettingsStore(tmp_path / f"settings-{len(instances)}.json")
        store.save(Settings(language=language))
        window = MainWindow(store, client_factory=client_factory, start_background=False)
        instances.append(window)
        qtbot.addWidget(window)
        window.show()
        return window

    create.releases = releases
    yield create
    for release in releases:
        release.set()
    for window in instances:
        if not isValid(window):
            continue
        window.close()
        qtbot.waitUntil(
            lambda window=window: (
                not isValid(window) or (not window.isVisible() and not window._jobs)
            ),
            timeout=6000,
        )


def test_catalog_placeholders_and_nonempty_translations():
    assert len(RU) > 180
    for source, translated in RU.items():
        assert translated.strip(), source

        def fields(template):
            return sorted(
                (name, spec, conv)
                for _, name, spec, conv in Formatter().parse(template)
                if name is not None
            )

        assert fields(source) == fields(translated), source


def test_static_captions_module_text_and_message_templates_have_catalog_entries(windows):
    window = windows()
    sources = set()
    for reference, message in window.i18n._bindings.values():
        if reference() is not None:
            sources.add(message.source if isinstance(message, Text) else str(message))
    for spec in MODULES:
        sources.update((spec.title, spec.description, spec.requirements, *spec.controls))
    sources.update(resolve_policy(profile).description for profile in PROFILE_NAMES)
    sources.add(resolve_policy("Smart", cpu_percent=99).description)
    root = Path(__file__).resolve().parents[1] / "src/nexus_ai"
    for path in root.rglob("*.py"):
        if path.name in ("translations.py", "i18n.py"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Text"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                sources.add(node.args[0].value)
    missing = []
    for source in sources:
        literal = re.sub(r"\{[^}]*\}", "", source)
        if (
            re.search(r"[A-Za-z]{2}", literal)
            and not source.startswith(("NEXUS", "N /"))
            and source not in RU
        ):
            missing.append(source)
    assert not missing, sorted(missing)


def test_default_and_legacy_settings_are_russian_without_destructive_migration(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    assert store.load().language == "ru"
    assert not store.path.exists()
    legacy = {"model": "llama3.2:3b", "profile": "Gaming", "ollama_url": "http://localhost:11434"}
    store.path.write_text(json.dumps(legacy))
    original = store.path.read_bytes()
    loaded = store.load()
    assert (
        loaded.language == "ru" and loaded.model == legacy["model"] and loaded.profile == "Gaming"
    )
    assert store.path.read_bytes() == original and store.warning is None
    store.save(replace(loaded, language="en"))
    assert store.load().language == "en"
    assert json.loads(store.path.read_text())["profile"] == "Gaming"


@pytest.mark.parametrize("invalid", ["de", "", None, [], 42])
def test_invalid_language_falls_back_without_losing_other_preferences(tmp_path, invalid):
    store = SettingsStore(tmp_path / "settings.json")
    data = {"language": invalid, "model": "my-model", "profile": "Eco"}
    store.path.write_text(json.dumps(data))
    assert store.load() == Settings(model="my-model", profile="Eco")
    assert "language" in store.warning
    assert "Некорректные" in render(store.warning, "ru")
    assert json.loads(store.path.read_text()) == data
    with pytest.raises(ValueError):
        validate_settings(replace(Settings(), language=invalid))


def test_language_switch_is_per_window_persistent_and_keeps_profile_ids(windows):
    russian, english = windows(), windows("en")
    assert russian.settings_button.text() == "Настройки"
    assert english.settings_button.text() == "Settings"
    assert russian.profile_combo.currentText() == "Умный"
    assert russian.profile_combo.currentData() == "Smart"
    russian.profile_combo.setCurrentIndex(russian.profile_combo.findData("Gaming"))
    assert russian.store.load().profile == "Gaming"
    russian.prompt.setPlainText("Save {Русский} <not markup>")
    russian.navigate("rgb")
    page, prompt = russian.stack.currentWidget(), russian.prompt.toPlainText()
    assert russian.set_language("en")
    assert russian.stack.currentWidget() is page and russian.prompt.toPlainText() == prompt
    assert russian.profile_combo.currentText() == "Gaming"
    assert any(label.text() == "System overview" for label in russian.findChildren(QLabel))
    assert russian.module_pages["rgb"].findChildren(QLabel)[2].text() == MODULES[1].description
    assert russian.store.load().language == "en"
    assert russian.set_language("ru")
    assert english.settings_button.text() == "Settings"
    assert russian.profile_combo.currentData() == "Gaming"
    assert russian.profile_combo.currentText() == "Игровой"
    assert all(not b.isEnabled() for p in russian.module_pages.values() for b in p.controls)
    assert not russian.fan_button.isEnabled()
    reopened = MainWindow(russian.store, start_background=False)
    assert reopened.settings_button.text() == "Настройки"
    reopened.close()


def test_settings_switches_instantly_and_cancel_keeps_language_but_not_draft_url(windows):
    window = windows()
    original = window.settings.ollama_url
    checked = []

    def interact():
        dialog = QApplication.activeModalWidget()
        language = dialog.findChild(QComboBox, "languageCombo")
        url = dialog.findChild(QLineEdit, "serverUrl")
        url.setText("http://draft-only.test:11434")
        language.setCurrentIndex(language.findData("en"))
        checked.append(window.settings_button.text())
        assert dialog.windowTitle() == "Settings"
        assert url.text() == "http://draft-only.test:11434"
        assert window.store.load().language == "en"
        language.setCurrentIndex(language.findData("ru"))
        assert dialog.windowTitle() == "Настройки"
        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons.button(QDialogButtonBox.StandardButton.Save).text() == "Сохранить"
        language.setCurrentIndex(language.findData("en"))
        dialog.reject()

    QTimer.singleShot(0, interact)
    window.open_settings()
    assert checked == ["Settings"]
    assert window.settings.language == "en" and window.store.load().language == "en"
    assert window.settings.ollama_url == original


def test_failed_language_persistence_reverts_selection_and_translates_error(windows, monkeypatch):
    window = windows()
    save = window.store.save

    def denied(_settings):
        raise PermissionError("file is busy")

    monkeypatch.setattr(window.store, "save", denied)
    checked = []

    def interact():
        dialog = QApplication.activeModalWidget()
        combo = dialog.findChild(QComboBox, "languageCombo")
        combo.setCurrentIndex(combo.findData("en"))
        assert combo.currentData() == "ru" and window.settings.language == "ru"
        assert "Настройки не сохранены" in dialog.findChild(QLabel, "settingsError").text()
        monkeypatch.setattr(window.store, "save", save)
        combo.setCurrentIndex(combo.findData("en"))
        assert window.settings.language == "en"
        assert not dialog.findChild(QLabel, "settingsError").text()
        checked.append(True)
        dialog.reject()

    QTimer.singleShot(0, interact)
    window.open_settings()
    assert checked == [True]


def test_context_menus_and_accessibility_follow_the_current_language(windows):
    window = windows()
    assert window.prompt.accessibleName() == "Сообщение"
    assert window.sidebar.buttons["assistant"].accessibleName() == "Открыть: Ассистент"
    menu = window.prompt.createStandardContextMenu()
    window.i18n.translate_menu(menu)
    assert any("Копировать" in action.text() for action in menu.actions())
    menu.deleteLater()
    window.set_language("en")
    assert window.prompt.accessibleName() == "Message"
    menu = window.prompt.createStandardContextMenu()
    window.i18n.translate_menu(menu)
    assert any("Copy" in action.text() for action in menu.actions())
    menu.deleteLater()


def test_runtime_errors_and_telemetry_retranslate_without_resampling(windows):
    window = windows()
    status = Text("CPU telemetry unavailable: {error}", error="external detail {raw}")
    snapshot = TelemetrySnapshot(
        None,
        50,
        1024**3,
        2 * 1024**3,
        1024**3,
        (GPUReading(0, "Actual GPU {model}", None, 1024**3, 2 * 1024**3, None),),
        Text("NVIDIA telemetry unavailable: {error}", error="driver detail"),
        cpu_status=status,
        temperatures=(TemperatureReading("Actual package name", 54.5),),
    )
    window._show_telemetry(snapshot)
    assert "Показания ЦП недоступны" in window.cpu_card.value.text()
    assert "ГиБ" in window.ram_card.value.text()
    assert "Видеопамять" in window._gpu_cards[0].value.text()
    assert "54,5" in window.temperature_values.text()
    error = OllamaClient._network_error(httpx.ConnectError("external connection detail"))
    job = OllamaJob("models", "http://localhost", lambda _: None)
    window._job_failed(job, error_text(error))
    assert "Не удаётся подключиться" in window.connection_status.text()
    history = list(window.history.points)
    window.set_language("en")
    assert "CPU telemetry unavailable" in window.cpu_card.value.text()
    assert "GiB" in window.ram_card.value.text()
    assert "Cannot reach Ollama" in window.connection_status.text()
    assert list(window.history.points) == history
    window.set_language("ru")
    assert "Не удаётся подключиться" in window.connection_status.text()
    assert "Actual GPU {model}" in window._gpu_cards[0].findChildren(QLabel)[0].text()


def test_switch_during_stream_keeps_model_request_context_and_user_content(windows, qtbot):
    release = Event()
    windows.releases.append(release)
    calls = []

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def list_models(self):
            return [OllamaModel("model:Русский-1", 1024**3)]

        def stream_chat(self, model, messages, **kwargs):
            calls.append((model, messages, kwargs["options"]))
            yield "Copy"
            release.wait(4)
            yield " Save {unchanged}"

    window = windows(client_factory=lambda _: Client())
    window.refresh_models()
    qtbot.waitUntil(lambda: not window._jobs)
    window.prompt.setPlainText("Save {my prompt}")
    window.send_message()
    qtbot.waitUntil(lambda: "Copy" in window.transcript.toPlainText())
    window.prompt.setPlainText("next draft")

    def interact():
        dialog = QApplication.activeModalWidget()
        assert not dialog.findChild(QLineEdit, "serverUrl").isEnabled()
        combo = dialog.findChild(QComboBox, "languageCombo")
        combo.setCurrentIndex(combo.findData("en"))
        assert window.prompt.toPlainText() == "next draft"
        assert "You\nSave {my prompt}" in window.transcript.toPlainText()
        assert "Copy" in window.transcript.toPlainText()
        dialog.reject()

    QTimer.singleShot(0, interact)
    window.open_settings()
    release.set()
    qtbot.waitUntil(lambda: not window._jobs)
    assert len(calls) == 1
    assert calls[0][0] == "model:Русский-1"
    assert window._messages[-1]["content"] == "Copy Save {unchanged}"
    window.set_language("ru")
    assert "Вы\nSave {my prompt}" in window.transcript.toPlainText()
    assert "Copy Save {unchanged}" in window.transcript.toPlainText()
    assert window.prompt.toPlainText() == "next draft"
    assert window.model_combo.currentData() == "model:Русский-1"
    assert "ГиБ" in window.model_combo.itemData(0, Qt.ItemDataRole.ToolTipRole)


def test_structured_messages_keep_raw_arguments_and_support_deepcopy():
    message = Text("Settings were not saved: {error}", error=Text("Model name must be text."))
    assert "Имя модели" in render(message, "ru")
    text = Text("You\n{prompt}\n\nNEXUS · {model}\n", prompt="Copy {hello}", model="model:English")
    clone = copy.deepcopy(text)
    assert "Copy {hello}" in render(clone, "ru")
    assert render(clone, "en") == str(text)
    combined = JoinedText((message, " RAW {details}"), "")
    assert render(copy.deepcopy(combined), "ru").endswith(" RAW {details}")


def test_protocol_errors_keep_structured_translations():
    client = OllamaClient(
        "http://localhost",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(404, json={"error": "external {detail}"})
        ),
    )
    with client, pytest.raises(OllamaError) as caught:
        list(client.stream_chat("my-model", []))
    ru = render(error_text(caught.value), "ru")
    assert "недоступна" in ru and "ollama pull my-model" in ru
    assert "external {detail}" in ru


def test_language_only_save_keeps_conversation_and_does_not_restart_discovery(windows):
    window = windows()
    window._messages = [{"role": "user", "content": "original question"}]
    window._append_transcript(
        Text("You\n{prompt}\n\nNEXUS · {model}\n", prompt="original question", model="model:1")
    )
    window.prompt.setPlainText("unfinished draft")
    checked = []

    def interact():
        dialog = QApplication.activeModalWidget()
        try:
            combo = dialog.findChild(QComboBox, "languageCombo")
            combo.setCurrentIndex(combo.findData("en"))
            buttons = dialog.findChild(QDialogButtonBox)
            buttons.button(QDialogButtonBox.StandardButton.Save).click()
            checked.append(True)
        finally:
            dialog.reject()

    QTimer.singleShot(0, interact)
    window.open_settings()
    assert checked == [True]
    assert window.settings.language == "en"
    assert window._messages == [{"role": "user", "content": "original question"}]
    assert "original question" in window.transcript.toPlainText()
    assert window.prompt.toPlainText() == "unfinished draft"
    assert not window._jobs and window._discovery_job is None


def test_compact_russian_layout_survives_switching_and_keeps_menu_bindings(windows, qtbot):
    window = windows()
    window.resize(780, 680)
    qtbot.waitUntil(lambda: window.chart_grid.columns == 1)
    assert window.sidebar.width() == 192
    menu = window.prompt.createStandardContextMenu()
    window.i18n.translate_menu(menu)
    window.set_language("en")
    assert any("Copy" in action.text() for action in menu.actions())
    assert window.sidebar.width() == 166
    window.set_language("ru")
    assert any("Копировать" in action.text() for action in menu.actions())
    assert window.sidebar.width() == 192
    assert window.prompt.width() > 100
    menu.deleteLater()


def test_scrollbar_menus_are_localized_and_retain_native_scroll_actions(windows):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QScrollBar

    window = windows()
    scrollbar = window.pages["overview"].verticalScrollBar()
    assert isinstance(scrollbar, QScrollBar)
    scrollbar.setRange(0, 100)
    scrollbar.setValue(50)
    menu = window.i18n.scrollbar_menu(scrollbar, QPoint(3, 30))
    bottom = next(action for action in menu.actions() if action.text() == "В конец")
    bottom.trigger()
    assert scrollbar.value() == 100
    window.set_language("en")
    top = next(action for action in menu.actions() if action.text() == "Top")
    top.trigger()
    assert scrollbar.value() == 0
    assert any(action.text() == "Scroll here" for action in menu.actions())
    menu.deleteLater()
