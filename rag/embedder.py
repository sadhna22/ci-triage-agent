"""Pluggable local embedder.

Primary (production / demo on your machine): sentence-transformers
`all-MiniLM-L6-v2` — the locked decision (offline, 384-dim, strong semantics).

Fallback (zero heavy deps): a deterministic char n-gram hashing vectorizer in pure
Python. It lets the whole RAG pipeline run and be tested anywhere torch isn't
installed. It is weaker than MiniLM but good enough to cluster normalized
signatures for the demo, and it keeps `retrieve.py` identical across both.

`get_embedder()` returns whichever is available; `.backend` says which.
"""
from __future__ import annotations

import hashlib
import math
import re

_MINILM = "all-MiniLM-L6-v2"


class _MiniLMEmbedder:
    backend = "minilm"
    dim = 384

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(_MINILM)

    def encode(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return [list(map(float, v)) for v in vecs]


class _HashingEmbedder:
    """Char 3-gram hashing -> fixed-dim L2-normalized vector. No deps."""

    backend = "hashing-fallback"
    dim = 512

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        text = re.sub(r"\s+", " ", text.lower()).strip()
        vec = [0.0] * self.dim
        grams = [text[i : i + 3] for i in range(max(len(text) - 2, 1))]
        for g in grams:
            h = int(hashlib.md5(g.encode()).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 1) & 1 else -1.0  # signed hashing reduces collisions
            vec[idx] += sign
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


_instance = None


def get_embedder():
    global _instance
    if _instance is not None:
        return _instance
    try:
        _instance = _MiniLMEmbedder()
    except Exception:
        _instance = _HashingEmbedder()
    return _instance


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # both are L2-normalized
