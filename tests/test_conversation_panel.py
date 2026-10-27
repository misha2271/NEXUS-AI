from __future__ import annotations

import threading

from nexus_ai.conversations import ConversationStore
from nexus_ai.ui.conversation_panel import ConversationPanel
from nexus_ai.ui.localization import Translator


def panel(qtbot, tmp_path):
    widget = ConversationPanel(Translator("en"), tmp_path / "conversations.db")
    qtbot.addWidget(widget)
    return widget


def wait(qtbot, widget):
    qtbot.waitUntil(lambda: not widget.busy, timeout=5000)


def test_completed_turns_are_serially_persisted_off_ui_thread(qtbot, tmp_path, monkeypatch):
    widget = panel(qtbot, tmp_path)
    owner = threading.get_ident()
    threads = []
    original = widget.store.save

    def save(*args, **kwargs):
        threads.append(threading.get_ident())
        return original(*args, **kwargs)

    monkeypatch.setattr(widget.store, "save", save)
    widget.save_turn("Привет\nraw", "Ответ один")
    widget.save_turn("Second", "Reply two")
    wait(qtbot, widget)
    store = ConversationStore(widget.store.path)
    summaries = store.list_conversations()
    assert len(summaries) == 1
    assert [message["content"] for message in store.load(summaries[0].id).messages] == [
        "Привет\nraw",
        "Ответ один",
        "Second",
        "Reply two",
    ]
    assert threads and all(thread != owner for thread in threads)
    assert widget.new_button.isEnabled()
    widget.shutdown()


def test_pending_old_save_cannot_replace_new_conversation(qtbot, tmp_path):
    widget = panel(qtbot, tmp_path)
    widget.save_turn("Old chat", "Old reply")
    widget.new_conversation()
    widget.save_turn("New chat", "New reply")
    wait(qtbot, widget)
    summaries = widget.store.list_conversations()
    assert len(summaries) == 2
    assert {summary.title for summary in summaries} == {"Old chat", "New chat"}
    assert widget.store.load(widget._identifier).title == "New chat"
    widget.shutdown()


def test_resume_preserves_raw_messages_and_appends_to_same_chat(qtbot, tmp_path):
    widget = panel(qtbot, tmp_path)
    widget.save_turn("raw <b> Привет", "Reply\n raw")
    wait(qtbot, widget)
    widget.new_conversation()
    received = []
    widget.loaded.connect(received.append)
    widget.load_selected()
    wait(qtbot, widget)
    assert received[0][0] == {"role": "user", "content": "raw <b> Привет"}
    widget.save_turn("Follow up", "Reply 2")
    wait(qtbot, widget)
    assert len(widget.store.list_conversations()) == 1
    assert len(widget.store.load(widget._identifier).messages) == 4
    widget.shutdown()


def test_shutdown_completes_queued_durable_saves(qtbot, tmp_path):
    widget = panel(qtbot, tmp_path)
    widget.save_turn("Saved during shutdown", "Completed answer")
    widget.shutdown()
    wait(qtbot, widget)
    assert widget.store.list_conversations()[0].title == "Saved during shutdown"
    assert not widget.new_button.isEnabled()


def test_delete_does_not_delete_another_selected_conversation(qtbot, tmp_path):
    widget = panel(qtbot, tmp_path)
    widget.save_turn("First", "One")
    widget.new_conversation()
    widget.save_turn("Second", "Two")
    wait(qtbot, widget)
    identifier = widget._identifier
    widget.delete_selected(confirm=False)
    wait(qtbot, widget)
    summaries = widget.store.list_conversations()
    assert len(summaries) == 1 and summaries[0].id != identifier
    assert widget._messages == []
    widget.shutdown()


def test_chat_busy_prevents_context_switch(qtbot, tmp_path):
    widget = panel(qtbot, tmp_path)
    widget._messages = [{"role": "user", "content": "active"}]
    widget.set_chat_busy(True)
    widget.new_conversation()
    assert widget._messages[0]["content"] == "active"
    assert not widget.new_button.isEnabled()
    widget.shutdown()


def test_conversation_actions_reflow_in_compact_russian_layout(qtbot, tmp_path):
    widget = ConversationPanel(Translator("ru"), tmp_path / "conversations.db")
    qtbot.addWidget(widget)
    widget.resize(420, 300)
    widget.show()
    qtbot.waitUntil(lambda: widget.actions.columns == 1)
    assert widget.width() == 420
    for button in widget.actions.widgets:
        assert button.geometry().right() <= widget.actions.width()
    widget.shutdown()
