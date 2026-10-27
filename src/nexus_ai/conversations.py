"""Transactional, local conversation persistence without changing message contents.

Connections are short-lived and owned by the calling worker. There is no global
SQLite connection, and no network request, migration of an unknown database, or
silent corruption recovery. The desktop should save completed turns explicitly.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import time
import uuid
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from nexus_ai.i18n import Text
from nexus_ai.settings import default_settings_path

_APPLICATION_ID = 0x4E585341
_SCHEMA_VERSION = 1


class ConversationError(Exception):
    """A validation, storage, or unsupported-schema error safe to show in the UI."""


class ConversationConflict(ConversationError):
    """A stale revision must not silently replace a newer completed conversation."""


@dataclass(frozen=True)
class ConversationSummary:
    id: str
    title: str
    created_at: float
    updated_at: float
    revision: int
    message_count: int


@dataclass(frozen=True)
class Conversation:
    id: str
    title: str
    messages: tuple[dict[str, str], ...]
    created_at: float
    updated_at: float
    revision: int


class ConversationStore:
    def __init__(
        self,
        path: Path | None = None,
        *,
        max_conversations: int = 100,
        max_messages: int = 400,
        max_message_chars: int = 65_536,
        max_conversation_chars: int = 1_000_000,
        max_database_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        self.path = (
            Path(path)
            if path is not None
            else default_settings_path().with_name("conversations.sqlite3")
        )
        self.max_conversations = max_conversations
        self.max_messages = max_messages
        self.max_message_chars = max_message_chars
        self.max_conversation_chars = max_conversation_chars
        self.max_database_bytes = max_database_bytes
        if any(
            type(value) is not int or value <= 0
            for value in (
                max_conversations,
                max_messages,
                max_message_chars,
                max_conversation_chars,
                max_database_bytes,
            )
        ):
            raise ValueError("Conversation limits must be positive integers")
        if max_database_bytes < 16_384:
            raise ValueError("Conversation database limit must be at least 16384 bytes")

    @contextmanager
    def _connection(self, *, write: bool = False):
        connection = None
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.path.is_symlink():
                raise ConversationError(Text("Conversation storage must not be a symbolic link."))
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(descriptor)
            if self.path.stat().st_size > self.max_database_bytes:
                raise ConversationError(
                    Text("Conversation storage exceeds the configured size limit.")
                )
            connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            self._ensure_schema(connection)
            page_size = connection.execute("PRAGMA page_size").fetchone()[0]
            connection.execute(f"PRAGMA max_page_count = {self.max_database_bytes // page_size}")
            yield connection
            connection.commit()
        except (ConversationError, ValueError):
            if connection is not None:
                connection.rollback()
            raise
        except (sqlite3.Error, OSError) as exc:
            if connection is not None:
                connection.rollback()
            raise ConversationError(
                Text(
                    "Conversation storage failed; existing data was preserved: {error}",
                    error=str(exc) or type(exc).__name__,
                )
            ) from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        application_id = connection.execute("PRAGMA application_id").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if application_id == 0 and version == 0 and not tables:
            connection.execute("""
                CREATE TABLE conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    messages TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision >= 0),
                    message_count INTEGER NOT NULL CHECK (message_count >= 0)
                )
            """)
            connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
        elif application_id != _APPLICATION_ID or version != _SCHEMA_VERSION:
            raise ConversationError(
                Text("Conversation storage has an unsupported schema; the file was preserved.")
            )
        elif (
            tables != {"conversations"}
            or connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('trigger', 'view')"
            ).fetchone()[0]
        ):
            raise ConversationError(
                Text("Conversation storage has an unsupported schema; the file was preserved.")
            )

    @staticmethod
    def _identifier(value: object) -> str:
        if not isinstance(value, str):
            raise ConversationError(Text("Choose a valid conversation identifier."))
        try:
            parsed = uuid.UUID(value)
        except (ValueError, AttributeError) as exc:
            raise ConversationError(Text("Choose a valid conversation identifier.")) from exc
        if str(parsed) != value:
            raise ConversationError(Text("Choose a valid conversation identifier."))
        return value

    @staticmethod
    def _title(value: object) -> str:
        if not isinstance(value, str) or len(value) > 200 or any(ord(c) < 32 for c in value):
            raise ConversationError(
                Text("Conversation titles must be text of at most 200 characters.")
            )
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ConversationError(
                Text("Conversation titles must contain valid Unicode text.")
            ) from exc
        return value

    def _messages(self, messages: Iterable[Mapping[str, str]]) -> tuple[dict[str, str], ...]:
        if not isinstance(messages, (list, tuple)):
            raise ConversationError(Text("Conversation messages must be a list of chat messages."))
        if len(messages) > self.max_messages:
            raise ConversationError(Text("This conversation exceeds the configured message limit."))
        normalized = []
        total = 0
        for message in messages:
            if not isinstance(message, Mapping) or set(message) != {"role", "content"}:
                raise ConversationError(
                    Text("Conversation messages need only role and content fields.")
                )
            role, content = message["role"], message["content"]
            if role not in ("user", "assistant") or not isinstance(content, str):
                raise ConversationError(
                    Text("Conversation messages must contain user or assistant text.")
                )
            if len(content) > self.max_message_chars:
                raise ConversationError(
                    Text("A conversation message exceeds the configured text limit.")
                )
            total += len(content)
            if total > self.max_conversation_chars:
                raise ConversationError(
                    Text("This conversation exceeds the configured text limit.")
                )
            try:
                content.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ConversationError(
                    Text("Conversation messages must contain valid Unicode text.")
                ) from exc
            normalized.append({"role": role, "content": content})
        return tuple(normalized)

    def _decode(self, row) -> Conversation:
        try:
            identifier, title, payload, created, updated, revision, count = row
            self._identifier(identifier)
            self._title(title)
            messages = self._messages(json.loads(payload))
            if count != len(messages) or type(revision) is not int or revision < 0:
                raise ValueError("Invalid conversation metadata")
            if (
                not isinstance(created, (int, float))
                or not isinstance(updated, (int, float))
                or not math.isfinite(created)
                or not math.isfinite(updated)
                or updated < created
            ):
                raise ValueError("Invalid conversation timestamps")
            return Conversation(identifier, title, messages, created, updated, revision)
        except (ValueError, TypeError, ConversationError) as exc:
            raise ConversationError(
                Text("Stored conversation data is invalid; the file was preserved.")
            ) from exc

    @staticmethod
    def _select(connection: sqlite3.Connection, identifier: str):
        return connection.execute(
            "SELECT id, title, messages, created_at, updated_at, revision, message_count "
            "FROM conversations WHERE id = ?",
            (identifier,),
        ).fetchone()

    def create(self, title: str = "") -> Conversation:
        title = self._title(title)
        identifier, now = str(uuid.uuid4()), time.time()
        with self._connection(write=True) as connection:
            count = connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            if count >= self.max_conversations:
                raise ConversationError(
                    Text("Conversation storage is full; delete an old chat first.")
                )
            connection.execute(
                "INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?, ?)",
                (identifier, title, "[]", now, now, 0, 0),
            )
        return Conversation(identifier, title, (), now, now, 0)

    def list_conversations(self, limit: int = 50) -> tuple[ConversationSummary, ...]:
        if type(limit) is not int or not 1 <= limit <= self.max_conversations:
            raise ConversationError(Text("Choose a valid conversation list limit."))
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id, title, messages, created_at, updated_at, revision, message_count "
                "FROM conversations ORDER BY updated_at DESC, id ASC LIMIT ?",
                (limit,),
            ).fetchall()
            conversations = tuple(self._decode(row) for row in rows)
        return tuple(
            ConversationSummary(
                c.id, c.title, c.created_at, c.updated_at, c.revision, len(c.messages)
            )
            for c in conversations
        )

    def load(self, identifier: str) -> Conversation:
        identifier = self._identifier(identifier)
        with self._connection() as connection:
            row = self._select(connection, identifier)
            if row is None:
                raise ConversationError(Text("This conversation no longer exists."))
            return self._decode(row)

    def save(
        self,
        identifier: str,
        messages: Iterable[Mapping[str, str]],
        *,
        title: str | None = None,
        expected_revision: int | None = None,
    ) -> Conversation:
        identifier = self._identifier(identifier)
        messages = self._messages(messages)
        if title is not None:
            title = self._title(title)
        if expected_revision is not None and (
            type(expected_revision) is not int or expected_revision < 0
        ):
            raise ConversationError(Text("Choose a valid conversation revision."))
        payload = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
        with self._connection(write=True) as connection:
            row = self._select(connection, identifier)
            if row is None:
                raise ConversationError(Text("This conversation no longer exists."))
            current = self._decode(row)
            if expected_revision is not None and current.revision != expected_revision:
                raise ConversationConflict(
                    Text("This conversation changed in another operation; reload it before saving.")
                )
            now = max(time.time(), current.updated_at)
            connection.execute(
                "UPDATE conversations SET title=?, messages=?, updated_at=?, revision=?, "
                "message_count=? WHERE id=?",
                (
                    current.title if title is None else title,
                    payload,
                    now,
                    current.revision + 1,
                    len(messages),
                    identifier,
                ),
            )
            result = Conversation(
                identifier,
                current.title if title is None else title,
                messages,
                current.created_at,
                now,
                current.revision + 1,
            )
        return result

    def delete(self, identifier: str) -> bool:
        identifier = self._identifier(identifier)
        with self._connection(write=True) as connection:
            return (
                connection.execute("DELETE FROM conversations WHERE id=?", (identifier,)).rowcount
                == 1
            )
