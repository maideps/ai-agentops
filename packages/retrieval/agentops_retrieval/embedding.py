"""Embedders. ``HashingEmbedder`` is deterministic and offline: no model download, no network.

It is lexical (feature hashing of word tokens), not semantic; it exists so mock mode, CI and
replays retrieve the same chunks every time (D-008). A semantic embedder plugs into the same
``Embedder`` protocol with its own ``model_id`` and dimension.
"""

import hashlib
import math
import re
from collections import Counter
from collections.abc import Sequence
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
        "which",
        "who",
        "what",
        "why",
        "how",
        "all",
        "any",
        "each",
        "every",
    }
)


class Embedder(Protocol):
    model_id: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def tokens(text: str) -> list[str]:
    """Lower-case word tokens without stopwords; a trailing plural ``s`` is dropped."""
    words = [word for word in _TOKEN.findall(text.lower()) if word not in _STOPWORDS]
    return [word[:-1] if len(word) > 4 and word.endswith("s") else word for word in words]


class HashingEmbedder:
    model_id = "hashing-v1-256"
    dimensions = 256

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token, count in Counter(tokens(text)).items():
            digest = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
            sign = 1.0 if (digest >> 63) & 1 else -1.0
            vector[digest % self.dimensions] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


def to_pgvector(vector: Sequence[float]) -> str:
    """pgvector text literal, rounded so the stored value is identical on every platform."""
    return "[" + ",".join(f"{value:.6f}" for value in vector) + "]"
