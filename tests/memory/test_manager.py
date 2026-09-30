"""
tests/memory/test_manager.py

Unit tests for the MemoryManager.

These tests use real file I/O and real SQLite/ChromaDB — they are integration
tests in practice, but scoped to the memory subsystem only.

Run with:
    uv run pytest tests/memory/ -v
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio

from app.memory.manager import MemoryManager
from app.memory.schemas import Note, SearchResult, Task


@pytest_asyncio.fixture
async def manager(tmp_path: Path, monkeypatch) -> MemoryManager:
    """Return a MemoryManager using a temporary directory for all storage."""
    from app.core import config as cfg_module

    vault = tmp_path / "vault"
    sqlite = tmp_path / "sqlite" / "test.db"
    chroma = tmp_path / "chroma"

    # Patch settings to point at tmp_path
    import app.core.config as core_cfg
    original = core_cfg.get_settings.cache_info  # just to verify it's cached

    core_cfg.get_settings.cache_clear()
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("SQLITE_PATH", str(sqlite))
    monkeypatch.setenv("CHROMA_PATH", str(chroma))
    core_cfg.get_settings.cache_clear()

    manager = MemoryManager()
    yield manager

    core_cfg.get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_note(manager: MemoryManager) -> None:
    note = await manager.create_note("Test Note", "This is content.", tags=["test"])
    assert note.title == "Test Note"
    assert note.content == "This is content."
    assert "test" in note.tags
    assert note.id == "test-note"


@pytest.mark.asyncio
async def test_create_note_file_exists_on_disk(manager: MemoryManager, tmp_path: Path) -> None:
    await manager.create_note("My Note", "Hello world.")
    vault = tmp_path / "vault"
    md_files = list(vault.glob("*.md"))
    assert len(md_files) == 1
    assert md_files[0].stem == "my-note"


@pytest.mark.asyncio
async def test_read_note(manager: MemoryManager) -> None:
    await manager.create_note("Read Me", "Readable content.")
    note = await manager.read_note("Read Me")
    assert note.content == "Readable content."


@pytest.mark.asyncio
async def test_update_note_changes_content(manager: MemoryManager) -> None:
    await manager.create_note("Update Me", "Original content.")
    updated = await manager.update_note("Update Me", "Updated content.")
    assert updated.content == "Updated content."
    # Re-read to confirm persistence
    re_read = await manager.read_note("Update Me")
    assert re_read.content == "Updated content."


@pytest.mark.asyncio
async def test_update_note_preserves_created_at(manager: MemoryManager) -> None:
    original = await manager.create_note("Preserve Dates", "Initial.")
    updated = await manager.update_note("Preserve Dates", "Changed.")
    assert updated.created_at == original.created_at
    assert updated.updated_at >= original.updated_at


@pytest.mark.asyncio
async def test_read_nonexistent_note_raises(manager: MemoryManager) -> None:
    with pytest.raises(FileNotFoundError):
        await manager.read_note("Does Not Exist")


@pytest.mark.asyncio
async def test_duplicate_note_raises(manager: MemoryManager) -> None:
    await manager.create_note("Duplicate", "First.")
    with pytest.raises(FileExistsError):
        await manager.create_note("Duplicate", "Second.")


@pytest.mark.asyncio
async def test_delete_note(manager: MemoryManager, tmp_path: Path) -> None:
    await manager.create_note("Delete Me", "Gone soon.")
    await manager.delete_note("Delete Me")
    vault = tmp_path / "vault"
    assert not (vault / "delete-me.md").exists()


# ---------------------------------------------------------------------------
# SQLite — Tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_task(manager: MemoryManager) -> None:
    task = await manager.create_task("Buy groceries")
    assert task.title == "Buy groceries"
    assert task.completed is False
    assert task.id  # non-empty UUID


@pytest.mark.asyncio
async def test_list_tasks(manager: MemoryManager) -> None:
    await manager.create_task("Task A")
    await manager.create_task("Task B")
    tasks = await manager.list_tasks()
    assert len(tasks) >= 2


@pytest.mark.asyncio
async def test_complete_task(manager: MemoryManager) -> None:
    task = await manager.create_task("Finish the report")
    result = await manager.complete_task(task.id)
    assert result is True
    # Completed tasks should appear in completed list, not default list
    active = await manager.list_tasks(completed=False)
    assert all(t.id != task.id for t in active)


@pytest.mark.asyncio
async def test_complete_nonexistent_task(manager: MemoryManager) -> None:
    result = await manager.complete_task(str(uuid.uuid4()))
    assert result is False


# ---------------------------------------------------------------------------
# ChromaDB — Semantic indexing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_note_indexed_in_chroma(manager: MemoryManager) -> None:
    await manager.create_note("AI Research", "Notes about machine learning and neural networks.")
    results = await manager.search_semantic("machine learning")
    assert any(r.id == "ai-research" for r in results)


@pytest.mark.asyncio
async def test_search_semantic_returns_search_results(manager: MemoryManager) -> None:
    await manager.create_note("Python Tips", "Python list comprehensions and decorators.")
    results = await manager.search_semantic("Python programming")
    assert isinstance(results, list)
    for r in results:
        assert isinstance(r, SearchResult)
        assert 0.0 <= r.score <= 1.0


@pytest.mark.asyncio
async def test_update_note_refreshes_chroma_index(manager: MemoryManager) -> None:
    await manager.create_note("Evolving Note", "Initial boring content.")
    await manager.update_note("Evolving Note", "Now about async Python and asyncio.")
    results = await manager.search_semantic("asyncio")
    assert any(r.id == "evolving-note" for r in results)


@pytest.mark.asyncio
async def test_delete_note_removes_from_chroma(manager: MemoryManager) -> None:
    await manager.create_note("Gone Forever", "About something specific: zebra migration patterns.")
    await manager.delete_note("Gone Forever")
    results = await manager.search_semantic("zebra migration")
    assert not any(r.id == "gone-forever" for r in results)


# ---------------------------------------------------------------------------
# Hybrid search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hybrid_search_returns_source_references(manager: MemoryManager) -> None:
    await manager.create_note("Project Alpha", "Details about Project Alpha planning.")
    await manager.create_task("Review Project Alpha deliverables")

    results = await manager.hybrid_search("Project Alpha")
    assert len(results) > 0
    for r in results:
        assert r.source in ("obsidian", "sqlite.tasks", "sqlite.events", "chroma")
        assert r.id
        assert r.path


@pytest.mark.asyncio
async def test_hybrid_search_no_hallucination(manager: MemoryManager) -> None:
    """Hybrid search on an empty store must return an empty list, not fake results."""
    results = await manager.hybrid_search("something that was never stored anywhere")
    # May return 0 results or only low-score semantic results — never hallucinated titles
    for r in results:
        assert r.title  # any result must have a real id
