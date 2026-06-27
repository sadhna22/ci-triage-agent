"""search_past_failures — threshold-gated top-k retrieval.

Two interchangeable backends, same output shape:
  * Chroma (production) — used when chromadb is importable AND an index exists.
  * In-memory fallback — embeds rag/corpus/*.json on first call with the local
    embedder (MiniLM or hashing) and ranks by cosine. No index build needed.

The similarity threshold is what lets the agent legitimately conclude
"no strong precedent" and fall back to other tools (makes Scenario 2's skip real).
"""
from __future__ import annotations

from rag.embedder import cosine, get_embedder
from rag.index import CHROMA_DIR, COLLECTION, load_corpus
from rag.normalize import normalize

# Cosine floor below which a match is "weak / no real precedent".
# MiniLM normalized cosine and the hashing fallback have different scales, so the
# threshold is backend-aware. Tune on Day 2 against the real corpus.
_THRESHOLDS = {"minilm": 0.55, "hashing-fallback": 0.40}

_fallback_index = None  # [(record, vector)]


def _threshold() -> float:
    return _THRESHOLDS.get(get_embedder().backend, 0.5)


def _try_chroma(query: str, k: int):
    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except Exception:
        return None
    try:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        col = client.get_collection(COLLECTION, embedding_function=ef)
        res = col.query(query_texts=[query], n_results=k)
    except Exception:
        return None  # index not built yet -> caller falls back

    out = []
    for id_, dist, meta, doc in zip(
        res["ids"][0], res["distances"][0], res["metadatas"][0], res["documents"][0]
    ):
        sim = 1.0 - dist
        out.append(_row(id_, doc, sim, meta))
    return out


def _build_fallback():
    global _fallback_index
    records = load_corpus()
    emb = get_embedder()
    vecs = emb.encode([r["signature"] for r in records])
    _fallback_index = list(zip(records, vecs))


def _search_fallback(query: str, k: int):
    if _fallback_index is None:
        _build_fallback()
    qv = get_embedder().encode([normalize(query)])[0]
    scored = [(cosine(qv, v), r) for r, v in _fallback_index]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        _row(r["id"], r["signature"], sim, r) for sim, r in scored[:k]
    ]


def _row(id_, signature, sim, meta) -> dict:
    return {
        "id": id_,
        "signature": signature,
        "similarity": round(float(sim), 3),
        "strong_precedent": float(sim) >= _threshold(),
        "verdict": meta.get("verdict", ""),
        "root_cause": meta.get("root_cause", ""),
        "owner": meta.get("owner", ""),
        "date": meta.get("date", ""),
        "fix_ref": meta.get("fix_ref", ""),
    }


def search(query: str, k: int = 5) -> list[dict]:
    """Return up to k past failures most similar to `query`, with similarity."""
    q = normalize(query)
    via_chroma = _try_chroma(q, k)
    return via_chroma if via_chroma is not None else _search_fallback(q, k)
