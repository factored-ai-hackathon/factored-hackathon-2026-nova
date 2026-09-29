"""Chat sessions. In memory for the MVP; the interface lets DynamoDB replace it later."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol

Lang = Literal["es", "pt"]


@dataclass
class Session:
    id: str
    lang: Lang
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SessionStore(Protocol):
    async def create(self, lang: Lang) -> Session: ...
    async def get(self, session_id: str) -> Session | None: ...
    async def set_lang(self, session_id: str, lang: Lang) -> None: ...


class InMemorySessionStore:
    """Process-local store. Sessions are lost on restart and not shared across instances."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def create(self, lang: Lang) -> Session:
        session = Session(id=str(uuid.uuid4()), lang=lang)
        self._sessions[session.id] = session
        return session

    async def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    async def set_lang(self, session_id: str, lang: Lang) -> None:
        self._sessions[session_id].lang = lang


_store = InMemorySessionStore()


def get_session_store() -> SessionStore:
    # TODO: return a DynamoDB-backed store when sessions must survive restarts.
    return _store
