"""Russian catalog coverage for v1 worker errors and the mobile client."""

from nexus_ai.i18n import Text, render
from nexus_ai.remote import WEB_MESSAGES, _page
from nexus_ai.translations import RU
from nexus_ai.ui.localization import Translator


def test_mobile_client_has_complete_russian_catalog_and_defaults_to_russian():
    assert all(message in RU for message in WEB_MESSAGES)
    assert all(render(message, "ru") != message for message in WEB_MESSAGES)
    page = _page().decode("utf-8")
    assert '<html lang="ru">' in page
    assert "lang='ru'" in page
    assert "Токен сопряжения" in page


def test_existing_worker_message_switches_without_translating_raw_identifiers(qtbot):
    from PySide6.QtWidgets import QLabel

    translator = Translator("ru")
    status = QLabel()
    qtbot.addWidget(status)
    message = Text("Game detected: {game}", game="My Game.exe")
    translator.bind(status, message)
    assert status.text() == "Обнаружена игра: My Game.exe"
    translator.set_language("en")
    assert status.text() == "Game detected: My Game.exe"
    translator.set_language("ru")
    assert status.text() == "Обнаружена игра: My Game.exe"
