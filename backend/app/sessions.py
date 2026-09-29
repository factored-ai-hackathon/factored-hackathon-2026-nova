"""Chat sessions and their conversation history (the agent's memory).

memory: process-local, for local development and tests. dynamodb: one item per session in the
sessions table, so conversations survive cold starts and are shared by every Lambda instance.
Sessions expire after `session_ttl_hours` without activity.
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Literal, Protocol

from app.config import Settings, get_settings

Lang = Literal["es", "pt"]
Role = Literal["user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str


@dataclass
class Session:
    id: str
    lang: Lang
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    messages: list[ChatMessage] = field(default_factory=list)
    auth: dict = field(default_factory=dict)  # identity verification state


class SessionStore(Protocol):
    async def create(self, lang: Lang, auth: dict | None = None) -> Session:
        """New session; `auth` is its initial verification state (the logged-in customer)."""
        ...

    async def get(self, session_id: str) -> Session | None: ...
    async def set_lang(self, session_id: str, lang: Lang) -> None: ...

    async def save_messages(
        self, session_id: str, lang: Lang, messages: list[ChatMessage], auth: dict | None = None
    ) -> None:
        """Replace the conversation history and verification state (creating the session if it
        doesn't exist)."""
        ...


class InMemorySessionStore:
    """Process-local store. Sessions are lost on restart and not shared across instances."""

    def __init__(self, max_messages: int = 40) -> None:
        self._sessions: dict[str, Session] = {}
        self.max_messages = max_messages

    async def create(self, lang: Lang, auth: dict | None = None) -> Session:
        session = Session(id=str(uuid.uuid4()), lang=lang, auth=dict(auth or {}))
        self._sessions[session.id] = session
        return session

    async def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    async def set_lang(self, session_id: str, lang: Lang) -> None:
        self._sessions[session_id].lang = lang

    async def save_messages(
        self, session_id: str, lang: Lang, messages: list[ChatMessage], auth: dict | None = None
    ) -> None:
        session = self._sessions.setdefault(session_id, Session(id=session_id, lang=lang))
        session.messages = list(messages[-self.max_messages :])
        session.auth = dict(auth or {})


class DynamoSessionStore:
    """One item per session: session_id (PK), lang, created_at, messages (JSON), expires_at."""

    def __init__(self, table: Any, ttl_hours: int, max_messages: int) -> None:
        self.table = table  # boto3 DynamoDB Table resource
        self.ttl_seconds = ttl_hours * 3600
        self.max_messages = max_messages

    def _expires_at(self) -> int:
        return int(time.time()) + self.ttl_seconds

    def _create(self, lang: Lang, auth: dict | None) -> Session:
        session = Session(id=str(uuid.uuid4()), lang=lang, auth=dict(auth or {}))
        self.table.put_item(
            Item={
                "session_id": session.id,
                "lang": lang,
                "created_at": session.created_at.isoformat(),
                "messages": "[]",
                "auth_state": json.dumps(session.auth),
                "expires_at": self._expires_at(),
            },
            ConditionExpression="attribute_not_exists(session_id)",
        )
        return session

    def _get(self, session_id: str) -> Session | None:
        item = self.table.get_item(Key={"session_id": session_id}, ConsistentRead=True).get("Item")
        # TTL deletes items up to a few days late: treat expired ones as gone.
        if item is None or int(item["expires_at"]) < time.time():
            return None
        return Session(
            id=item["session_id"],
            lang=item["lang"],
            created_at=datetime.fromisoformat(item["created_at"]),
            messages=[ChatMessage(**m) for m in json.loads(item.get("messages", "[]"))],
            auth=json.loads(item.get("auth_state", "{}")),
        )

    def _set_lang(self, session_id: str, lang: Lang) -> None:
        self.table.update_item(
            Key={"session_id": session_id},
            UpdateExpression="SET lang = :lang, expires_at = :exp",
            ExpressionAttributeValues={":lang": lang, ":exp": self._expires_at()},
        )

    def _save_messages(
        self, session_id: str, lang: Lang, messages: list[ChatMessage], auth: dict | None
    ) -> None:
        kept = [{"role": m.role, "content": m.content} for m in messages[-self.max_messages :]]
        self.table.update_item(
            Key={"session_id": session_id},
            UpdateExpression=(
                "SET messages = :m, auth_state = :auth, lang = if_not_exists(lang, :lang), "
                "expires_at = :exp, created_at = if_not_exists(created_at, :now)"
            ),
            ExpressionAttributeValues={
                ":m": json.dumps(kept, ensure_ascii=False),
                # "auth" is a DynamoDB reserved word, hence auth_state.
                ":auth": json.dumps(auth or {}),
                ":lang": lang,
                ":exp": self._expires_at(),
                ":now": datetime.now(UTC).isoformat(),
            },
        )

    async def create(self, lang: Lang, auth: dict | None = None) -> Session:
        return await asyncio.to_thread(self._create, lang, auth)

    async def get(self, session_id: str) -> Session | None:
        return await asyncio.to_thread(self._get, session_id)

    async def set_lang(self, session_id: str, lang: Lang) -> None:
        await asyncio.to_thread(self._set_lang, session_id, lang)

    async def save_messages(
        self, session_id: str, lang: Lang, messages: list[ChatMessage], auth: dict | None = None
    ) -> None:
        await asyncio.to_thread(self._save_messages, session_id, lang, messages, auth)


def build_session_store(settings: Settings) -> SessionStore:
    if settings.sessions_store == "dynamodb":
        import boto3

        table = boto3.resource("dynamodb", region_name=settings.aws_region).Table(
            settings.sessions_table
        )
        return DynamoSessionStore(table, settings.session_ttl_hours, settings.max_history_messages)
    return InMemorySessionStore(settings.max_history_messages)


@lru_cache
def get_session_store() -> SessionStore:
    return build_session_store(get_settings())
