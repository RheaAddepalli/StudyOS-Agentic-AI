"""Persistent learner state.

Deliberately boring: one table, one row per learner, the whole LearnerState
serialized as JSON. Two backends share this file because they share
everything except the connection and the upsert syntax:

- SQLite (default, `db_path`) — zero setup, used by pytest and local CLI use.
- Postgres (when `DATABASE_URL` is set, e.g. a Neon connection string) — used
  in production, because a deployed web service's local disk isn't
  guaranteed to survive a restart or redeploy the way a real database is.

`get_store()` picks one based on config; the rest of the app (api.py, cli.py)
only ever calls the shared `StateStoreBase` interface — save / load /
load_or_create / list_learner_ids — so nothing else needs to know or care
which backend is active.
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from .schemas import LearnerState


class StateStoreBase(ABC):
    @abstractmethod
    def save(self, state: LearnerState) -> None: ...

    @abstractmethod
    def load(self, learner_id: str) -> LearnerState | None: ...

    def load_or_create(self, learner_id: str) -> LearnerState:
        return self.load(learner_id) or LearnerState(learner_id=learner_id)

    @abstractmethod
    def list_learner_ids(self) -> list[str]: ...


# ---------------------------------------------------------------------------
# SQLite backend
# ---------------------------------------------------------------------------

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS learner_state (
    learner_id TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


@contextmanager
def _sqlite_connect(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_SQLITE_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


class SQLiteStateStore(StateStoreBase):
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.db_path
        with _sqlite_connect(self.db_path):
            pass  # ensures the table exists on construction

    def save(self, state: LearnerState) -> None:
        state.updated_at = datetime.now(timezone.utc)
        payload = state.model_dump_json()
        with _sqlite_connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO learner_state (learner_id, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(learner_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (state.learner_id, payload, state.updated_at.isoformat()),
            )

    def load(self, learner_id: str) -> LearnerState | None:
        with _sqlite_connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT state_json FROM learner_state WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()
        if row is None:
            return None
        return LearnerState.model_validate(json.loads(row[0]))

    def list_learner_ids(self) -> list[str]:
        with _sqlite_connect(self.db_path) as conn:
            rows = conn.execute("SELECT learner_id FROM learner_state").fetchall()
        return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Postgres backend
# ---------------------------------------------------------------------------

_POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS learner_state (
    learner_id TEXT PRIMARY KEY,
    state_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
"""


class PostgresStateStore(StateStoreBase):
    def __init__(self, database_url: str | None = None):
        # Imported lazily so `psycopg2` is only a hard dependency when
        # Postgres is actually configured — SQLite-only setups (tests, local
        # CLI use) don't need it installed at all.
        import psycopg2
        import psycopg2.pool

        self._psycopg2 = psycopg2
        self.database_url = database_url or settings.database_url
        self._pool = psycopg2.pool.SimpleConnectionPool(1, 10, self.database_url)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(_POSTGRES_SCHEMA)
            conn.commit()

    @contextmanager
    def _connect(self):
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    def save(self, state: LearnerState) -> None:
        state.updated_at = datetime.now(timezone.utc)
        payload = state.model_dump_json()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO learner_state (learner_id, state_json, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (learner_id) DO UPDATE SET
                    state_json = EXCLUDED.state_json,
                    updated_at = EXCLUDED.updated_at
                """,
                (state.learner_id, payload, state.updated_at),
            )
            conn.commit()

    def load(self, learner_id: str) -> LearnerState | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT state_json FROM learner_state WHERE learner_id = %s",
                (learner_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        raw = row[0]
        # psycopg2 auto-decodes JSONB to a dict; handle both cases defensively.
        data = raw if isinstance(raw, dict) else json.loads(raw)
        return LearnerState.model_validate(data)

    def list_learner_ids(self) -> list[str]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT learner_id FROM learner_state")
            rows = cur.fetchall()
        return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Backwards-compatible name + factory
# ---------------------------------------------------------------------------

# Kept so existing imports (`from .state import StateStore`) don't need to
# change everywhere that only ever used the SQLite backend directly (tests,
# and the CLI when run without DATABASE_URL set).
StateStore = SQLiteStateStore

_store_singleton: StateStoreBase | None = None


def get_store() -> StateStoreBase:
    """Returns the Postgres store if DATABASE_URL is set, else SQLite.
    Cached as a singleton so the connection pool isn't rebuilt per request."""
    global _store_singleton
    if _store_singleton is None:
        if settings.database_url:
            _store_singleton = PostgresStateStore(settings.database_url)
        else:
            _store_singleton = SQLiteStateStore(settings.db_path)
    return _store_singleton
