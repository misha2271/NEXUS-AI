"""Persistence tests use actual SQLite, including concurrency and failed transactions."""

from __future__ import annotations

import os
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from nexus_ai.conversations import ConversationConflict, ConversationError, ConversationStore


def test_conversations_survive_new_store_instances_and_preserve_exact_text(tmp_path):
    path = tmp_path / "nested" / "conversations.db"
    store = ConversationStore(path)
    assert not path.exists()
    first = store.create("Разговор ' ; DROP TABLE conversations; --")
    messages = [
        {"role": "user", "content": "Привет!\n {keep raw} <script> Save 🖤"},
        {"role": "assistant", "content": "  Ответ\t\nРусский / English\x00"},
    ]
    updated = store.save(first.id, messages, expected_revision=0)
    assert updated.revision == 1 and updated.messages == tuple(messages)
    assert updated.created_at == first.created_at <= updated.updated_at
    messages[0]["content"] = "changed outside storage"
    reopened = ConversationStore(path)
    restored = reopened.load(first.id)
    assert restored == updated
    summaries = reopened.list_conversations()
    assert len(summaries) == 1
    assert summaries[0].message_count == 2 and summaries[0].title == first.title
    assert summaries[0].revision == 1
    renamed = reopened.save(first.id, restored.messages, title="Новое имя", expected_revision=1)
    assert renamed.title == "Новое имя" and renamed.revision == 2
    assert renamed.messages == updated.messages


def test_new_database_uses_private_posix_permissions(tmp_path):
    store = ConversationStore(tmp_path / "private" / "conversations.db")
    store.create()
    if os.name != "nt":
        assert store.path.stat().st_mode & 0o777 == 0o600
        assert store.path.parent.stat().st_mode & 0o777 == 0o700


def test_missing_and_malformed_ids_never_create_conversations(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")
    with pytest.raises(ConversationError, match="no longer exists"):
        store.load(str(uuid.uuid4()))
    with pytest.raises(ConversationError, match="identifier"):
        store.load("../../settings.json")
    assert store.list_conversations() == ()


@pytest.mark.parametrize(
    "messages",
    [
        None,
        {},
        "not a list",
        [{"role": "system", "content": "hidden instruction"}],
        [{"role": "user", "content": None}],
        [{"role": "tool", "content": "tool result"}],
        [{"role": "user", "content": "text", "secret": "unexpected field"}],
        [{"role": [], "content": "invalid role type"}],
        [{"role": "user", "content": "\ud800"}],
    ],
)
def test_invalid_messages_do_not_replace_valid_data(tmp_path, messages):
    store = ConversationStore(tmp_path / "conversations.db")
    chat = store.create("Existing")
    saved = store.save(chat.id, [{"role": "user", "content": "preserved"}])
    with pytest.raises(ConversationError):
        store.save(chat.id, messages)
    assert store.load(chat.id) == saved


@pytest.mark.parametrize("title", [[], None, "a" * 201, "title\nnot one line", "\ud800"])
def test_invalid_titles_do_not_touch_store(tmp_path, title):
    store = ConversationStore(tmp_path / "conversations.db")
    with pytest.raises(ConversationError):
        store.create(title)
    assert not store.path.exists()


def test_revisions_prevent_stale_worker_overwrite(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")
    chat = store.create()
    one = store.save(chat.id, [{"role": "user", "content": "first"}], expected_revision=0)
    with pytest.raises(ConversationConflict, match="reload"):
        store.save(chat.id, [{"role": "user", "content": "stale"}], expected_revision=0)
    assert store.load(chat.id) == one
    with pytest.raises(ConversationError, match="revision"):
        store.save(chat.id, [], expected_revision=True)


def test_limits_are_enforced_before_saving_and_deleted_slots_can_be_reused(tmp_path):
    store = ConversationStore(
        tmp_path / "conversations.db",
        max_conversations=2,
        max_messages=2,
        max_message_chars=5,
        max_conversation_chars=8,
    )
    first, second = store.create("first"), store.create("second")
    with pytest.raises(ConversationError, match="full"):
        store.create("third")
    with pytest.raises(ConversationError, match="message limit"):
        store.save(first.id, [{"role": "user", "content": "a"}] * 3)
    with pytest.raises(ConversationError, match="message exceeds"):
        store.save(first.id, [{"role": "user", "content": "123456"}])
    with pytest.raises(ConversationError, match="conversation exceeds"):
        store.save(
            first.id,
            [
                {"role": "user", "content": "12345"},
                {"role": "assistant", "content": "1234"},
            ],
        )
    assert store.load(first.id).messages == ()
    assert store.delete(first.id)
    assert not store.delete(first.id)
    third = store.create("third")
    assert {s.id for s in store.list_conversations(limit=2)} == {second.id, third.id}
    with pytest.raises(ConversationError, match="list limit"):
        store.list_conversations(limit=3)


def test_database_size_limit_rolls_back_failed_write(tmp_path):
    store = ConversationStore(tmp_path / "small.db", max_database_bytes=16_384)
    chat = store.create()
    with pytest.raises(ConversationError, match="storage failed"):
        store.save(chat.id, [{"role": "user", "content": "x" * 60_000}])
    assert store.load(chat.id).revision == 0
    assert store.load(chat.id).messages == ()
    assert store.path.stat().st_size <= 16_384


def test_corrupt_and_foreign_databases_are_not_replaced(tmp_path):
    path = tmp_path / "corrupt.db"
    content = b"not SQLite: original user bytes"
    path.write_bytes(content)
    with pytest.raises(ConversationError, match="preserved"):
        ConversationStore(path).list_conversations()
    assert path.read_bytes() == content
    foreign = tmp_path / "foreign.db"
    with sqlite3.connect(foreign) as connection:
        connection.execute("CREATE TABLE unrelated(secret TEXT)")
        connection.execute("INSERT INTO unrelated VALUES ('original')")
    original = foreign.read_bytes()
    with pytest.raises(ConversationError, match="unsupported schema"):
        ConversationStore(foreign).list_conversations()
    assert foreign.read_bytes() == original


def test_unsupported_future_schema_and_corrupt_messages_fail_closed(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")
    chat = store.create()
    with sqlite3.connect(store.path) as connection:
        connection.execute("PRAGMA user_version=99")
    original = store.path.read_bytes()
    with pytest.raises(ConversationError, match="unsupported schema"):
        store.load(chat.id)
    assert store.path.read_bytes() == original
    with sqlite3.connect(store.path) as connection:
        connection.execute("PRAGMA user_version=1")
        connection.execute(
            "UPDATE conversations SET messages=? WHERE id=?", ("broken JSON", chat.id)
        )
    with pytest.raises(ConversationError, match="invalid"):
        store.load(chat.id)
    with pytest.raises(ConversationError, match="invalid"):
        store.save(
            chat.id, []
        )  # never overwrite an invalid record with an apparent successful chat
    with sqlite3.connect(store.path) as connection:
        assert (
            connection.execute("SELECT messages FROM conversations").fetchone()[0] == "broken JSON"
        )


def test_unexpected_triggers_are_not_executed(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")
    first, second = store.create("first"), store.create("second")
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "CREATE TRIGGER hostile AFTER UPDATE ON conversations "
            "BEGIN DELETE FROM conversations; END"
        )
    with pytest.raises(ConversationError, match="unsupported schema"):
        store.save(first.id, [])
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 2
    assert second.id != first.id


def test_independent_worker_connections_serialize_concurrent_writes(tmp_path):
    store = ConversationStore(tmp_path / "conversations.db")

    def task(index):
        chat = store.create(f"worker {index}")
        return store.save(chat.id, [{"role": "user", "content": str(index)}], expected_revision=0)

    with ThreadPoolExecutor(max_workers=4) as pool:
        conversations = list(pool.map(task, range(12)))
    assert len(store.list_conversations()) == 12
    for chat in conversations:
        assert store.load(chat.id) == chat


def test_database_file_cannot_be_a_symlink(tmp_path):
    target = tmp_path / "user-file"
    target.write_bytes(b"preserve me")
    path = tmp_path / "conversations.db"
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation needs platform privileges")
    with pytest.raises(ConversationError, match="symbolic link"):
        ConversationStore(path).create()
    assert target.read_bytes() == b"preserve me"


def test_oversize_existing_database_is_not_opened_or_replaced(tmp_path):
    path = tmp_path / "too-big.db"
    original = b"x" * 20_000
    path.write_bytes(original)
    with pytest.raises(ConversationError, match="size limit"):
        ConversationStore(path, max_database_bytes=16_384).list_conversations()
    assert path.read_bytes() == original
