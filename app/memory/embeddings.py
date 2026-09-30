"""
app/memory/embeddings.py

Local embedding generator using sentence-transformers.
No Ollama, no network calls after first model download.

Default model: all-MiniLM-L6-v2 (22M params, 384-dim, fast on CPU)
"""

from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("memory.embeddings")


import torch


def _resolve_device() -> str:
    settings = get_settings()
    if settings.device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return settings.device


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Return the singleton SentenceTransformer model."""
    settings = get_settings()
    device = _resolve_device()
    logger.info("embedding_model_load", model=settings.embedding_model, device=device)
    model = SentenceTransformer(settings.embedding_model, device=device)
    logger.info("embedding_model_ready", model=settings.embedding_model, device=device)
    return model


def embed(text: str) -> list[float]:
    """Embed a single text string into a float vector.

    Args:
        text: The text to embed. Will be truncated by the model if too long.

    Returns:
        A list of floats representing the embedding vector.
    """
    model = _get_model()
    vector = model.encode(text, convert_to_numpy=True)
    return vector.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts in a single batch for efficiency.

    Args:
        texts: List of strings to embed.

    Returns:
        List of embedding vectors, one per input text.
    """
    model = _get_model()
    vectors = model.encode(texts, convert_to_numpy=True, batch_size=32)
    return [v.tolist() for v in vectors]
