"""
app/memory/manager.py

The SINGLE public gateway to all memory operations.

No other module may directly import SQLiteStore, ChromaStore, or ObsidianStore.
Every memory operation goes through this class.

Public API matches plan.md §8:
    memory.create_note()
    memory.read_note()
    memory.update_note()
    memory.create_task()
    memory.search_semantic()
    memory.hybrid_search()
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

from app.core.logging import get_logger
from app.memory.chroma import ChromaStore
from app.memory.obsidian import ObsidianStore
from app.memory.schemas import Note, SearchResult, Task
from app.memory.sqlite import SQLiteStore

logger = get_logger("memory.manager")


class MemoryManager:
    """Single gateway to all memory subsystems.

    Instantiate once per application. All subsystems are lazy-initialised
    on first use so startup is fast.
    """

    def __init__(self) -> None:
        self._obsidian = ObsidianStore()
        self._sqlite = SQLiteStore()
        self._chroma = ChromaStore()
        self._sqlite_ready = False

    async def _ensure_sqlite(self) -> None:
        if not self._sqlite_ready:
            await self._sqlite.init_schema()
            self._sqlite_ready = True

    # ------------------------------------------------------------------
    # Notes (Obsidian + ChromaDB index)
    # ------------------------------------------------------------------

    async def create_note(
        self,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> Note:
        """Create a new markdown note and index it for semantic search.

        The canonical text lives in Obsidian (data/vault/).
        Only the embedding vector + metadata are stored in ChromaDB.

        Raises:
            FileExistsError: If a note with this title already exists.
        """
        with logger.timed("create_note", title=title):
            note = await self._obsidian.create_note(title, content, tags)
            # Index in Chroma — embed content, store only id/source/path
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._chroma.index(
                    doc_id=note.id,
                    source="obsidian",
                    path=f"data/vault/{note.id}.md",
                    text=f"{note.title}\n{note.content}",
                ),
            )
        return note

    async def read_note(self, title: str) -> Note:
        """Read a note by title from the Obsidian vault.

        Raises:
            FileNotFoundError: If the note does not exist.
        """
        with logger.timed("read_note", title=title):
            return await self._obsidian.read_note(title)

    async def update_note(
        self,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> Note:
        """Update an existing note and refresh its embedding in ChromaDB.

        Raises:
            FileNotFoundError: If the note does not exist.
        """
        with logger.timed("update_note", title=title):
            note = await self._obsidian.update_note(title, content, tags)
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._chroma.index(
                    doc_id=note.id,
                    source="obsidian",
                    path=f"data/vault/{note.id}.md",
                    text=f"{note.title}\n{note.content}",
                ),
            )
        return note

    async def delete_note(self, title: str) -> None:
        """Delete a note from the vault and remove it from the index."""
        with logger.timed("delete_note", title=title):
            note = await self._obsidian.read_note(title)
            await self._obsidian.delete_note(title)
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._chroma.delete(note.id)
            )

    # ------------------------------------------------------------------
    # Tasks (SQLite)
    # ------------------------------------------------------------------

    async def create_task(self, title: str, due: str | None = None) -> Task:
        """Create a structured task in SQLite.

        Args:
            title: Task description.
            due:   Optional ISO 8601 due datetime string.
        """
        await self._ensure_sqlite()
        with logger.timed("create_task", title=title):
            return await self._sqlite.create_task(title, due)

    async def complete_task(self, task_id: str) -> bool:
        """Mark a task as completed. Returns True if the task was found."""
        await self._ensure_sqlite()
        return await self._sqlite.complete_task(task_id)

    async def list_tasks(self, completed: bool = False) -> list[Task]:
        """List tasks filtered by completion status."""
        await self._ensure_sqlite()
        return await self._sqlite.list_tasks(completed)

    # ------------------------------------------------------------------
    # Semantic search (ChromaDB)
    # ------------------------------------------------------------------

    async def search_semantic(
        self, query: str, n_results: int = 5
    ) -> list[SearchResult]:
        """Vector similarity search across all indexed content.

        Returns source references with relevance scores.
        Canonical text is NOT stored in ChromaDB — resolve from `path` if needed.
        """
        with logger.timed("search_semantic", query=query[:60], n=n_results):
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._chroma.search(query, n_results),
            )

    # ------------------------------------------------------------------
    # Hybrid search (SQLite + Obsidian keyword + ChromaDB vector)
    # ------------------------------------------------------------------

    async def hybrid_search(self, query: str) -> list[SearchResult]:
        """Three-stage hybrid search: exact → keyword → semantic.

        Pipeline (plan.md §9):
            1. SQLite exact title match
            2. Obsidian keyword search across .md files
            3. ChromaDB vector similarity
            4. Merge, deduplicate by id, sort by score descending.

        Every result includes a source reference. Memory is never hallucinated.
        """
        with logger.timed("hybrid_search", query=query[:60]):
            await self._ensure_sqlite()

            results_by_id: dict[str, SearchResult] = {}

            # --- Stage 1: SQLite exact task title match ---
            tasks = await self._sqlite.list_tasks(completed=False)
            for task in tasks:
                if query.lower() in task.title.lower():
                    results_by_id[task.id] = SearchResult(
                        id=task.id,
                        source="sqlite.tasks",
                        path=f"sqlite://tasks/{task.id}",
                        title=task.title,
                        snippet=f"Task: {task.title}",
                        score=1.0,
                    )

            # --- Stage 2: Obsidian keyword search ---
            notes = await self._obsidian.search_notes(query)
            for note in notes:
                if note.id not in results_by_id:
                    snippet = note.content[:120].replace("\n", " ")
                    results_by_id[note.id] = SearchResult(
                        id=note.id,
                        source="obsidian",
                        path=f"data/vault/{note.id}.md",
                        title=note.title,
                        snippet=snippet,
                        score=0.85,
                    )

            # --- Stage 3: ChromaDB vector similarity ---
            semantic = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._chroma.search(query, n_results=5),
            )
            for result in semantic:
                if result.id not in results_by_id:
                    results_by_id[result.id] = result
                else:
                    # Boost score if already found by keyword/exact
                    existing = results_by_id[result.id]
                    boosted = min(1.0, existing.score + result.score * 0.1)
                    results_by_id[result.id] = SearchResult(
                        id=existing.id,
                        source=existing.source,
                        path=existing.path,
                        title=existing.title,
                        snippet=existing.snippet,
                        score=round(boosted, 4),
                    )

            # --- Merge + sort ---
            merged = sorted(
                results_by_id.values(), key=lambda r: r.score, reverse=True
            )

        return merged
