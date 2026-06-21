"""Milestone 2 — Redis as long-term memory.

Switched to RedisVL after the raw redis-py + RediSearch KNN path returned
zero results despite confirmed correct indexing (num_docs matched,
zero indexing failures, byte lengths matched exactly). RedisVL is the
officially recommended high-level client for vector search on Redis and
handles query-building/serialization internally, so it sidesteps whatever
was going wrong at that layer.

Two jobs, same as before:
  1. Persist every session so nothing is lost.
  2. Store node embeddings so we can semantically search past thoughts.
"""
import json
import os
import time
import numpy as np
import redis
from redisvl.index import SearchIndex
from redisvl.query import VectorQuery
from sentence_transformers import SentenceTransformer
from anthropic import Anthropic

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(REDIS_URL)
_anthropic = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

INDEX_NAME = "node_idx_redisvl"   # new name — fresh index, no leftover state
PREFIX = "node:"
DIM = 384  # all-MiniLM-L6-v2 output size

_local_model = SentenceTransformer("all-MiniLM-L6-v2")


def _embed(text: str) -> bytes:
    """Real semantic embedding via a local model — no API key, no billing.
    For storage_type="hash", RedisVL needs the vector pre-packed as raw
    bytes (lists only work for JSON-storage indexes)."""
    vec = _local_model.encode(text, normalize_embeddings=True).astype(np.float32)
    return vec.tobytes()


_schema = {
    "index": {"name": INDEX_NAME, "prefix": PREFIX, "storage_type": "hash"},
    "fields": [
        {"name": "text", "type": "text"},
        {"name": "detail", "type": "text"},
        {"name": "type", "type": "tag"},
        {"name": "session_id", "type": "tag"},
        {"name": "ts", "type": "numeric"},
        {"name": "embedding", "type": "vector",
         "attrs": {"dims": DIM, "distance_metric": "cosine",
                   "algorithm": "hnsw", "datatype": "float32"}},
    ],
}

_index = None


def _get_index() -> SearchIndex:
    global _index
    if _index is None:
        _index = SearchIndex.from_dict(_schema, redis_url=REDIS_URL)
    return _index


def ensure_index() -> None:
    """Create the vector index once. Safe to call on startup / every call."""
    _get_index().create(overwrite=False)


def save_session(session) -> None:
    """Store the full session blob + index each node for search."""
    r.set(f"session:{session.id}", session.model_dump_json())
    records = []
    for node in session.nodes:
        records.append({
            "id": node.id,
            "text": node.text,
            "detail": node.detail,
            "type": node.type.value,
            "session_id": session.id,
            "ts": int(time.time()),
            "embedding": _embed(f"{node.text}. {node.detail}"),
        })
    _get_index().load(records, id_field="id")


def search_past(query_text: str, k: int = 5, exclude_session: str = "") -> list[dict]:
    """Return the k most semantically similar past nodes."""
    q = VectorQuery(
        vector=_embed(query_text),
        vector_field_name="embedding",
        num_results=k + (5 if exclude_session else 0),  # pad, then filter below
        return_fields=["text", "detail", "type", "session_id"],
        return_score=True,
    )
    results = _get_index().query(q)
    out = []
    for res in results:
        if res.get("session_id") == exclude_session:
            continue
        out.append({
            "text": res["text"], "detail": res["detail"], "type": res["type"],
            "session_id": res["session_id"], "score": float(res["vector_distance"]),
        })
        if len(out) >= k:
            break
    return out


def get_session(session_id: str):
    raw = r.get(f"session:{session_id}")
    return json.loads(raw) if raw else None