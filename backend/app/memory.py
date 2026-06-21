"""Milestone 2 — Redis as long-term memory.

Two jobs:
  1. Persist every committed session blob so nothing is lost.
  2. Store one embedding per topic so we can semantically search past thoughts.

Embedding text per topic:
  "{name}. {contribution}. {excerpt1} {excerpt2}. {concerns} {matching_actions}"

Uses RedisVL + local all-MiniLM-L6-v2 (384-dim, no API key, no billing).
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

# New topic-level index (clean break from old node_idx_redisvl schema)
INDEX_NAME = "tg_topic_idx"
PREFIX = "topic:"
DIM = 384  # all-MiniLM-L6-v2 output size

_local_model = SentenceTransformer("all-MiniLM-L6-v2")


def _embed(text: str) -> bytes:
    """Local sentence embedding — no API key needed.
    Hash-storage indexes require the vector pre-packed as raw bytes."""
    vec = _local_model.encode(text, normalize_embeddings=True).astype(np.float32)
    return vec.tobytes()


_schema = {
    "index": {"name": INDEX_NAME, "prefix": PREFIX, "storage_type": "hash"},
    "fields": [
        {"name": "name", "type": "tag"},
        {"name": "kind", "type": "tag"},
        {"name": "weight", "type": "numeric"},
        {"name": "session_id", "type": "tag"},
        {"name": "ts", "type": "numeric"},
        {"name": "contribution", "type": "text"},
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
    """Create the vector index once. Safe to call on every request."""
    _get_index().create(overwrite=False)


def save_session(session_id_or_session, data: dict | None = None) -> None:
    """Store session blob + index one embedding per topic.

    New call style (M2):  save_session(session_id: str, data: dict)
    Old call style (M1):  save_session(session: Session)  → no-op, schema incompatible.
    """
    if data is None:
        # Old Session-object call sites (/classify, /ws/transcribe) — skip silently.
        return

    session_id: str = session_id_or_session
    r.set(f"session:{session_id}", json.dumps(data))

    concerns = data.get("concerns", [])
    action_items = data.get("actionItems", [])
    ts = int(time.time())
    records = []

    for tp in data.get("topics", []):
        name = (tp.get("name") or "").strip().lower()
        if not name:
            continue

        contribution = tp.get("contribution", "")
        excerpts = tp.get("excerpts", [])

        # action items whose topic field matches this topic name
        matching_actions = [
            ai["text"] for ai in action_items
            if (ai.get("topic") or "").lower() == name
        ]

        # rich embedding: name + contribution + verbatim excerpts + session-level concerns + topic actions
        parts = [name]
        if contribution:
            parts.append(contribution)
        parts.extend(excerpts)
        if concerns:
            parts.append(" ".join(concerns))
        if matching_actions:
            parts.append(" ".join(matching_actions))

        embed_text = ". ".join(p for p in parts if p)

        records.append({
            "id": f"{session_id}::{name}",
            "name": name,
            "kind": tp.get("kind", "topic"),
            "weight": int(tp.get("weight", 2)),
            "session_id": session_id,
            "ts": ts,
            "contribution": contribution,
            "connects": json.dumps(tp.get("connects", [])),
            "embed_text": embed_text,
            "embedding": _embed(embed_text),
        })

    if records:
        _get_index().load(records, id_field="id")


def search_past(query_text: str, k: int = 5, exclude_session: str = "") -> list[dict]:
    """Return the k most semantically similar past topics across all sessions."""
    q = VectorQuery(
        vector=_embed(query_text),
        vector_field_name="embedding",
        num_results=k + (5 if exclude_session else 0),
        return_fields=["name", "contribution", "kind", "session_id"],
        return_score=True,
    )
    results = _get_index().query(q)
    out = []
    for res in results:
        if res.get("session_id") == exclude_session:
            continue
        out.append({
            "name": res.get("name", ""),
            "contribution": res.get("contribution", ""),
            "kind": res.get("kind", "topic"),
            "session_id": res.get("session_id", ""),
            "score": float(res.get("vector_distance", 1.0)),
        })
        if len(out) >= k:
            break
    return out


def get_session(session_id: str):
    raw = r.get(f"session:{session_id}")
    return json.loads(raw) if raw else None
