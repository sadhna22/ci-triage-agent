"""Build the Chroma index from rag/corpus/*.json.

Run: `python -m rag.index`

Embeds each record's `signature` with local all-MiniLM-L6-v2 (offline). Verdict /
owner / root_cause / date ride along as metadata (not embedded).
"""
from __future__ import annotations

import glob
import json
import os

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "corpus")
CHROMA_DIR = os.path.join(os.path.dirname(__file__), ".chroma")
COLLECTION = "past_failures"
EMBED_MODEL = "all-MiniLM-L6-v2"


def load_corpus() -> list[dict]:
    records = []
    for path in sorted(glob.glob(os.path.join(CORPUS_DIR, "*.json"))):
        with open(path) as f:
            data = json.load(f)
            records.extend(data if isinstance(data, list) else [data])
    return records


def build() -> int:
    import chromadb
    from chromadb.utils import embedding_functions

    records = load_corpus()
    if not records:
        raise SystemExit(f"No corpus records found in {CORPUS_DIR}")

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL
    )
    # Fresh build each time keeps the index a pure function of corpus/.
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    col = client.create_collection(COLLECTION, embedding_function=ef)

    col.add(
        ids=[r["id"] for r in records],
        documents=[r["signature"] for r in records],   # <- the embedded text
        metadatas=[
            {
                "verdict": r["verdict"],
                "root_cause": r.get("root_cause", ""),
                "owner": r.get("owner", ""),
                "date": r.get("date", ""),
                "fix_ref": r.get("fix_ref", ""),
            }
            for r in records
        ],
    )
    print(f"Indexed {len(records)} records into '{COLLECTION}' at {CHROMA_DIR}")
    return len(records)


if __name__ == "__main__":
    build()
