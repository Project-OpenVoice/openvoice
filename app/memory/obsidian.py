"""
app/memory/obsidian.py

File-based CRUD for markdown notes stored in the Obsidian vault (data/vault/).

Rules (from plan.md):
- Markdown only — never store structured data here.
- Never duplicate canonical text in SQLite or ChromaDB.
- Each note is one .md file; filename = slug derived from title.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
import aiofiles.os

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.models import utcnow
from app.memory.schemas import Note

logger = get_logger("memory.obsidian")


def _slugify(title: str) -> str:
    """Convert a note title to a safe filename slug.

    Example: "Meeting Notes 2026" → "meeting-notes-2026"
    """
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "untitled"


def _note_path(vault: Path, title: str) -> Path:
    return vault / f"{_slugify(title)}.md"


def _render_frontmatter(note: Note) -> str:
    """Render YAML frontmatter + content for the .md file."""
    tags_str = ", ".join(note.tags) if note.tags else ""
    return (
        f"---\n"
        f"id: {note.id}\n"
        f"title: {note.title}\n"
        f"tags: [{tags_str}]\n"
        f"created_at: {note.created_at.isoformat()}\n"
        f"updated_at: {note.updated_at.isoformat()}\n"
        f"---\n\n"
        f"{note.content}\n"
    )


def _parse_note_file(path: Path, raw: str) -> Note:
    """Parse a .md file with YAML frontmatter into a Note."""
    import yaml  # optional dep; falls back to manual parse

    lines = raw.split("\n")
    if lines[0].strip() == "---":
        end = lines.index("---", 1)
        fm_text = "\n".join(lines[1:end])
        content = "\n".join(lines[end + 1 :]).strip()
        try:
            fm = yaml.safe_load(fm_text) or {}
        except Exception:
            fm = {}
    else:
        fm = {}
        content = raw

    slug = path.stem
    now = utcnow()
    return Note(
        id=fm.get("id", slug),
        title=fm.get("title", slug),
        content=content,
        tags=fm.get("tags") or [],
        created_at=fm.get("created_at", now),
        updated_at=fm.get("updated_at", now),
    )


class ObsidianStore:
    """Async CRUD for markdown notes in the Obsidian vault directory."""

    def __init__(self) -> None:
        self._vault = Path(get_settings().vault_path)

    async def _ensure_vault(self) -> None:
        self._vault.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_note(
        self,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> Note:
        """Create a new note. Raises FileExistsError if it already exists."""
        await self._ensure_vault()
        path = _note_path(self._vault, title)

        if path.exists():
            raise FileExistsError(
                f"Note already exists: {path.name}. Use update_note() to modify it."
            )

        now = utcnow()
        note = Note(
            id=_slugify(title),
            title=title,
            content=content,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )

        with logger.timed("create_note", note_id=note.id):
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(_render_frontmatter(note))

        return note

    async def read_note(self, title: str) -> Note:
        """Read a note by title. Raises FileNotFoundError if not found."""
        path = _note_path(self._vault, title)

        with logger.timed("read_note", note_id=_slugify(title)):
            if not path.exists():
                raise FileNotFoundError(f"Note not found: {path.name}")
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                raw = await f.read()

        return _parse_note_file(path, raw)

    async def update_note(
        self,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> Note:
        """Update an existing note. Raises FileNotFoundError if not found."""
        path = _note_path(self._vault, title)

        if not path.exists():
            raise FileNotFoundError(
                f"Note not found: {path.name}. Use create_note() to create it."
            )

        # Read existing to preserve created_at
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()
        existing = _parse_note_file(path, raw)

        note = Note(
            id=existing.id,
            title=existing.title,
            content=content,
            tags=tags if tags is not None else existing.tags,
            created_at=existing.created_at,
            updated_at=utcnow(),
        )

        with logger.timed("update_note", note_id=note.id):
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(_render_frontmatter(note))

        return note

    async def search_notes(self, query: str) -> list[Note]:
        """Keyword search across all notes in the vault.

        Returns notes whose title or content contains the query string
        (case-insensitive). Ordered by filename.
        """
        await self._ensure_vault()
        query_lower = query.lower()
        results: list[Note] = []

        with logger.timed("search_notes", query=query):
            for path in sorted(self._vault.glob("*.md")):
                async with aiofiles.open(path, "r", encoding="utf-8") as f:
                    raw = await f.read()
                if query_lower in raw.lower():
                    results.append(_parse_note_file(path, raw))

        return results

    async def delete_note(self, title: str) -> None:
        """Delete a note by title. Raises FileNotFoundError if not found."""
        path = _note_path(self._vault, title)
        if not path.exists():
            raise FileNotFoundError(f"Note not found: {path.name}")
        with logger.timed("delete_note", note_id=_slugify(title)):
            path.unlink()
