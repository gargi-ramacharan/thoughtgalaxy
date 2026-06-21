"""Thought Galaxy backend — FastAPI.

Endpoints
  WS   /ws/transcribe   live mic audio in → transcript + nodes out   (M1)
  POST /classify        transcript → nodes (non-streaming fallback)  (M1)
  POST /suggest         tap a bubble, get one grounded next step     (M2)
  GET  /search          semantic search over past thoughts           (M2)
  POST /execute         run an agent on a task node                  (M3)

The WebSocket is the heart of the live demo. The REST routes make it easy to
test each layer in isolation (and give you a fallback path if the socket
misbehaves on stage).
"""
import os
import uuid
import json
import datetime
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
load_dotenv()

import app.observability  # noqa: F401  — initializes Sentry/Arize on import
from app.classify import classify_transcript
from app.extract import extract_thought
from app.llm import list_extractors
from app.schemas import Session, SuggestRequest, ExecuteRequest

app = FastAPI(title="Thought Galaxy")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session cache. Redis (memory.py) is the durable store once M2 lands.
SESSIONS: dict[str, Session] = {}


@app.get("/health")
def health():
    return {
        "ok": True,
        "extractors": list_extractors(),
        "claude_configured": bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()),
    }


# ─────────────────────────── Milestone 1 ───────────────────────────
@app.websocket("/ws/transcribe")
async def ws_transcribe(ws: WebSocket):
    """Live pipeline. Browser streams audio chunks; we stream back:
       {type:'partial', text}   interim words (the live-typing effect)
       {type:'nodes', nodes}    classified bubbles, after each pause
    """
    await ws.accept()
    from app.deepgram_stream import make_live_connection

    loop = asyncio.get_event_loop()
    accumulated: list[str] = []
    sid = str(uuid.uuid4())

    def on_transcript(text: str, is_final: bool):
        asyncio.run_coroutine_threadsafe(
            ws.send_json({"type": "partial", "text": text}), loop
        )
        if is_final:
            accumulated.append(text)

    def on_utterance_end():
        # speaker paused — classify what we have so far
        chunk = " ".join(accumulated).strip()
        if not chunk:
            return
        nodes = classify_transcript(chunk)
        asyncio.run_coroutine_threadsafe(
            ws.send_json(
                {"type": "nodes", "nodes": [n.model_dump() for n in nodes]}
            ),
            loop,
        )
        asyncio.run_coroutine_threadsafe(
            ws.send_json({"type": "session_id", "session_id": sid}),
            loop,
        )

    dg = await make_live_connection(on_transcript, on_utterance_end)

    try:
        while True:
            audio = await ws.receive_bytes()
            try:
                dg.send(audio)
            except Exception as e:
                print(f"[ws] dg.send failed: {e}")
                break
    except WebSocketDisconnect:
        pass
    finally:
        await dg.finish()
        # persist the finished session
        full = " ".join(accumulated).strip()
        if full:
            nodes = classify_transcript(full)
            session = Session(
                id=sid,
                created_at=datetime.datetime.utcnow().isoformat(),
                transcript=full,
                nodes=nodes,
            )
            SESSIONS[sid] = session
            try:
                from app.memory import save_session, ensure_index
                ensure_index()
                save_session(session)
            except Exception:
                pass  # Redis optional until M2


@app.post("/extract-thought")
def extract(payload: dict):
    """Mind-map note → topics/events/actions.

    Uses Claude when ANTHROPIC_API_KEY is set; falls back to a local
    rule-based parser when credits are exhausted or the key is missing.
    """
    text = (payload.get("text") or payload.get("transcript") or "").strip()
    if not text:
        return {"error": "text is required"}
    existing = payload.get("existing_topics") or []
    return extract_thought(text, existing)


@app.post("/classify")
def classify(payload: dict):
    """Non-streaming fallback: POST {transcript} → a saved session."""
    transcript = payload["transcript"]
    nodes = classify_transcript(transcript)
    sid = str(uuid.uuid4())
    session = Session(
        id=sid,
        created_at=datetime.datetime.utcnow().isoformat(),
        transcript=transcript,
        nodes=nodes,
    )
    SESSIONS[sid] = session
    try:
        from app.memory import save_session, ensure_index
        ensure_index()
        save_session(session)
    except Exception:
        pass
    return session.model_dump()


# ─────────────────────────── Milestone 2 ───────────────────────────
@app.post("/suggest")
def suggest(req: SuggestRequest):
    """Tap a bubble → one grounded next step (pulls past context)."""
    from app.suggest import suggest_for_node
    mem = SESSIONS.get(req.session_id)
    fallback = mem.model_dump() if mem else None
    return suggest_for_node(req.node_id, req.session_id, fallback=fallback).model_dump()


@app.get("/search")
def search(q: str):
    """Semantic search over all past thoughts."""
    from app.memory import search_past
    return {"results": search_past(q, k=8)}


# ─────────────────────────── Milestone 3 ───────────────────────────
@app.post("/execute")
async def execute(req: ExecuteRequest):
    """Route a task node to the right Fetch.ai agent and run it.

    In M3 this forwards to the calendar/email uAgents. Here we mark the node
    running and hand off; the agent pings back completion out of band.
    """
    session = SESSIONS.get(req.session_id)
    if not session:
        return {"error": "session not found"}
    node = next((n for n in session.nodes if n.id == req.node_id), None)
    if not node:
        return {"error": "node not found"}

    node.status = "running"
    # TODO (M3): publish to Fetch.ai agent via uAgents messaging.
    # See agents/calendar_agent.py and agents/email_agent.py.
    from app.agent_bridge import dispatch_task
    result = await dispatch_task(node)
    node.status = "done" if result.get("ok") else "failed"
    return {"node_id": node.id, "status": node.status, "result": result}
