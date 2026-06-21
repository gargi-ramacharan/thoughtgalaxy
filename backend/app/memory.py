"""Milestone 2 — Redis as long-term memory.

Two jobs:
  1. Persist every session so nothing is lost.
  2. Store node embeddings so we can semantically search past thoughts:
     "find when I was stressed about exams" pulls the right bubbles even if
     the words don't match exactly.

This is what lets the Insight Agent say "you've felt this way before, and last
time X helped." Without memory, suggestions are generic. With it, they feel
like the app actually knows you.

Uses redis-py with the RediSearch vector index (Redis Stack / Redis Cloud).
"""
import json
import os
import time
import numpy as np
import redis
from redis.commands.search.field import TextField, VectorField, TagField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from anthropic import Anthropic

r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
_anthropic = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

INDEX_NAME = "node_idx"
PREFIX = "node:"
DIM = 1024  # match your embedding model's output dim


def _embed(text: str) -> bytes:
    """Embed text to a vector. Swap this for whatever embedding API you use
    (Voyage, OpenAI, Cohere). Returns float32 bytes for Redis.

    Placeholder uses a deterministic hash-based vector so the pipeline runs
    end-to-end offline; replace before relying on real semantic quality.
    """
    # TODO: replace with a real embedding call, e.g. Voyage AI:
    #   vec = voyage.embed([text], model="voyage-3").embeddings[0]
    rng = np.random.default_rng(abs(hash(text)) % (2**32))
    vec = rng.standard_normal(DIM).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec.tobytes()


def ensure_index() -> None:
    """Create the vector index once. Safe to call on startup."""
    try:
        r.ft(INDEX_NAME).info()
    except redis.ResponseError:
        r.ft(INDEX_NAME).create_index(
            fields=[
                TextField("text"),
                TextField("detail"),
                TagField("type"),
                TextField("session_id"),
                VectorField(
                    "embedding",
                    "HNSW",
                    {"TYPE": "FLOAT32", "DIM": DIM, "DISTANCE_METRIC": "COSINE"},
                ),
            ],
            definition=IndexDefinition(prefix=[PREFIX], index_type=IndexType.HASH),
        )


def save_session(session) -> None:
    """Store the full session blob + index each node for search."""
    r.set(f"session:{session.id}", session.model_dump_json())
    for node in session.nodes:
        r.hset(
            f"{PREFIX}{node.id}",
            mapping={
                "text": node.text,
                "detail": node.detail,
                "type": node.type.value,
                "session_id": session.id,
                "ts": int(time.time()),
                "embedding": _embed(f"{node.text}. {node.detail}"),
            },
        )


def search_past(query_text: str, k: int = 5, exclude_session: str = "") -> list[dict]:
    """Return the k most semantically similar past nodes."""
    qvec = _embed(query_text)
    q = (
        Query(f"*=>[KNN {k} @embedding $vec AS score]")
        .sort_by("score")
        .return_fields("text", "detail", "type", "session_id", "score")
        .dialect(2)
    )
    res = r.ft(INDEX_NAME).search(q, query_params={"vec": qvec})
    out = []
    for doc in res.docs:
        if doc.session_id == exclude_session:
            continue
        out.append(
            {"text": doc.text, "detail": doc.detail, "type": doc.type,
             "session_id": doc.session_id, "score": float(doc.score)}
        )
    return out


def get_session(session_id: str):
    raw = r.get(f"session:{session_id}")
    return json.loads(raw) if raw else None
