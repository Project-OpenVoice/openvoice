"""
app/memory/sqlite.py

Async SQLite CRUD for structured state (tasks, events, devices, settings).

Rules:
- Never store markdown here -- canonical text lives in Obsidian.
- All access goes through manager.py -- never call this module directly.
- Uses aiosqlite for non-blocking async I/O.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import aiosqlite

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.models import utcnow
from app.memory.schemas import Event, Task

logger = get_logger("memory.sqlite")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    completed   INTEGER NOT NULL DEFAULT 0,
    due         TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    start       TEXT NOT NULL,
    end         TEXT,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    meta        TEXT NOT NULL DEFAULT '{}',
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relationships (
    id          TEXT PRIMARY KEY,
    from_id     TEXT NOT NULL,
    to_id       TEXT NOT NULL,
    kind        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""


class SQLiteStore:
    """Async SQLite CRUD for tasks and events.

    Each method opens and closes its own connection to avoid event-loop
    threading issues with aiosqlite across different async contexts.
    """

    def __init__(self) -> None:
        self._db_path = Path(get_settings().sqlite_path)

    def _db(self) -> str:
        """Return the database path as a string, ensuring parent dirs exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        return str(self._db_path)

    async def init_schema(self) -> None:
        """Create all tables if they don't exist. Safe to call on every startup."""
        async with aiosqlite.connect(self._db()) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.executescript(_SCHEMA_SQL)
            await conn.commit()
        logger.info("sqlite_schema_init", db=str(self._db_path))

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    async def create_task(self, title: str, due: str | None = None) -> Task:
        """Create a new task. `due` is an ISO 8601 datetime string or None."""
        now = utcnow()
        task = Task(
            id=str(uuid.uuid4()),
            title=title,
            completed=False,
            due=due,  # type: ignore[arg-type]
            created_at=now,
            updated_at=now,
        )

        with logger.timed("create_task", task_id=task.id):
            async with aiosqlite.connect(self._db()) as conn:
                await conn.execute(
                    "INSERT INTO tasks (id, title, completed, due, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        task.id,
                        task.title,
                        int(task.completed),
                        due,
                        task.created_at.isoformat(),
                        task.updated_at.isoformat(),
                    ),
                )
                await conn.commit()

        return task

    async def get_task(self, task_id: str) -> Task | None:
        """Return a task by ID, or None if not found."""
        async with aiosqlite.connect(self._db()) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ) as cur:
                row = await cur.fetchone()

        if row is None:
            return None

        return Task(
            id=row["id"],
            title=row["title"],
            completed=bool(row["completed"]),
            due=row["due"],  # type: ignore[arg-type]
            created_at=row["created_at"],  # type: ignore[arg-type]
            updated_at=row["updated_at"],  # type: ignore[arg-type]
        )

    async def complete_task(self, task_id: str) -> bool:
        """Mark a task as completed. Returns True if found and updated."""
        now = utcnow()
        async with aiosqlite.connect(self._db()) as conn:
            cur = await conn.execute(
                "UPDATE tasks SET completed = 1, updated_at = ? WHERE id = ?",
                (now.isoformat(), task_id),
            )
            await conn.commit()
        return cur.rowcount > 0

    async def list_tasks(self, completed: bool = False) -> list[Task]:
        """List tasks, filtered by completion status."""
        async with aiosqlite.connect(self._db()) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM tasks WHERE completed = ? ORDER BY created_at DESC",
                (int(completed),),
            ) as cur:
                rows = await cur.fetchall()

        return [
            Task(
                id=r["id"],
                title=r["title"],
                completed=bool(r["completed"]),
                due=r["due"],  # type: ignore[arg-type]
                created_at=r["created_at"],  # type: ignore[arg-type]
                updated_at=r["updated_at"],  # type: ignore[arg-type]
            )
            for r in rows
        ]

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task. Returns True if found and deleted."""
        async with aiosqlite.connect(self._db()) as conn:
            cur = await conn.execute(
                "DELETE FROM tasks WHERE id = ?", (task_id,)
            )
            await conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def create_event(
        self,
        title: str,
        start: str,
        end: str | None = None,
        description: str = "",
    ) -> Event:
        """Create a calendar event. `start`/`end` are ISO 8601 strings."""
        now = utcnow()
        event = Event(
            id=str(uuid.uuid4()),
            title=title,
            start=start,  # type: ignore[arg-type]
            end=end,  # type: ignore[arg-type]
            description=description,
            created_at=now,
            updated_at=now,
        )

        with logger.timed("create_event", event_id=event.id):
            async with aiosqlite.connect(self._db()) as conn:
                await conn.execute(
                    "INSERT INTO events (id, title, start, end, description, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.id,
                        event.title,
                        str(event.start),
                        str(event.end) if event.end else None,
                        event.description,
                        event.created_at.isoformat(),
                        event.updated_at.isoformat(),
                    ),
                )
                await conn.commit()

        return event

    async def list_events(self) -> list[Event]:
        """List all events ordered by start time."""
        async with aiosqlite.connect(self._db()) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM events ORDER BY start ASC"
            ) as cur:
                rows = await cur.fetchall()

        return [
            Event(
                id=r["id"],
                title=r["title"],
                start=r["start"],  # type: ignore[arg-type]
                end=r["end"],  # type: ignore[arg-type]
                description=r["description"],
                created_at=r["created_at"],  # type: ignore[arg-type]
                updated_at=r["updated_at"],  # type: ignore[arg-type]
            )
            for r in rows
        ]

    async def delete_event(self, event_id: str) -> bool:
        """Delete an event. Returns True if found and deleted."""
        async with aiosqlite.connect(self._db()) as conn:
            cur = await conn.execute(
                "DELETE FROM events WHERE id = ?", (event_id,)
            )
            await conn.commit()
        return cur.rowcount > 0
