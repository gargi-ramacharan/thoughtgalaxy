# memory.py — Redis vector memory. Powers Milestone 2:
# "pull semantically related moments from past sessions."
#
# This is also your Redis-prize centerpiece: real vector search + agent memory,
# not just caching.
#
#   remember(session_id, text, kind)  -> store one thought so it can be recalled later
#   search(query_text, k)             -> the k most semantically related past thoughts

import os
import time
import uuid

from redisvl.index import SearchIndex
from redisvl.query import VectorQuery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# text-embedding-3-small = 1536 dims. If you swap to the local MiniLM model
# below, change this to 384 (the schema reads it).
EMBED_DIMS = 1536


# --- embeddings: the ONE place to swap providers ---------------------------
_oai = None

def embed(text: str) -> list[float]:
    global _oai
    if _oai is None:
        from openai import OpenAI
        _oai = OpenAI()  # uses OPENAI_API_KEY
    resp = _oai.embeddings.create(model="text-embedding-3-small", input=text)
    return resp.data[0].embedding

    # --- local / no-API-key alternative (set EMBED_DIMS = 384 above) ---
    # from sentence_transformers import SentenceTransformer
    # global _model
    # _model = SentenceTransformer("all-MiniLM-L6-v2")
    # return _model.encode(text).tolist()


# --- the index --------------------------------------------------------------
_schema = {
    "index": {"name": "thoughts", "prefix": "thought", "storage_type": "hash"},
    "fields": [
        {"name": "session_id", "type": "tag"},
        {"name": "text", "type": "text"},
        {"name": "kind", "type": "tag"},
        {"name": "ts", "type": "numeric"},
        {"name": "embedding", "type": "vector",
         "attrs": {"dims": EMBED_DIMS, "distance_metric": "cosine",
                   "algorithm": "hnsw", "datatype": "float32"}},
    ],
}

_index = None

def get_index() -> SearchIndex:
    global _index
    if _index is None:
        _index = SearchIndex.from_dict(_schema, redis_url=REDIS_URL)
        try:
            _index.create(overwrite=False)   # safe to call on every startup
        except Exception:
            pass  # already exists
    return _index


# --- the two functions everyone else calls ---------------------------------
def remember(session_id: str, text: str, kind: str = "other") -> str:
    """Store one thought/topic so future sessions can semantically recall it."""
    rec = {
        "id": uuid.uuid4().hex,
        "session_id": session_id,
        "text": text,
        "kind": kind,
        "ts": time.time(),
        "embedding": embed(text),
    }
    get_index().load([rec], id_field="id")
    return rec["id"]


def search(query_text: str, k: int = 5) -> list[dict]:
    """Return the k most semantically related past thoughts (list of dicts
    with 'text', 'kind', 'session_id', 'vector_distance')."""
    q = VectorQuery(
        vector=embed(query_text),
        vector_field_name="embedding",
        num_results=k,
        return_fields=["text", "kind", "session_id", "ts"],
        return_score=True,
    )
    return get_index().query(q)


# quick smoke test:  python memory.py
if __name__ == "__main__":
    remember("demo", "I'm stressed about my flight on Sunday", kind="emotion")
    remember("demo", "Need to pack for the Tahoe trip", kind="task")
    for hit in search("travel plans", k=3):
        print(round(float(hit["vector_distance"]), 3), hit["text"])
