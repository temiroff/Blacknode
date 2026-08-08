"""Server-side sessions for Blacknode Cloud accounts in the local editor."""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class CloudSession:
    token: str
    expires_at: datetime
    account: dict[str, Any]


class CloudSessionStore:
    """Keep Cloud bearer tokens out of browser storage and JavaScript."""

    def __init__(self) -> None:
        self._sessions: dict[str, CloudSession] = {}
        self._lock = threading.RLock()

    def create(
        self,
        token: str,
        expires_at: str,
        account: dict[str, Any],
    ) -> tuple[str, CloudSession]:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        session_id = secrets.token_urlsafe(32)
        session = CloudSession(token=token, expires_at=expiry, account=dict(account))
        with self._lock:
            self._purge_locked()
            self._sessions[session_id] = session
        return session_id, session

    def get(self, session_id: str | None) -> CloudSession | None:
        if not session_id:
            return None
        with self._lock:
            self._purge_locked()
            return self._sessions.get(session_id)

    def pop(self, session_id: str | None) -> CloudSession | None:
        if not session_id:
            return None
        with self._lock:
            return self._sessions.pop(session_id, None)

    def _purge_locked(self) -> None:
        now = datetime.now(UTC)
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)
