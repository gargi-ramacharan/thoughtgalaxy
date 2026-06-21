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
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
load_dotenv()

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOGLE_CREDS_PATH = os.environ.get(
    "GOOGLE_CREDENTIALS_PATH",
    os.path.join(BACKEND_DIR, "google_credentials.json"),
)
GOOGLE_TOKEN_PATH = os.path.join(BACKEND_DIR, "token_calendar.json")
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
_cal_state: dict = {}

import app.observability  # noqa: F401
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

SESSIONS: dict[str, Session] = {}
SESSIONS_EXTRACT: dict[str, dict] = {}


def _merge_session(existing, new):
    """Accumulate committed thoughts into one session blob so /suggest can
    find any bubble on the map, not just the latest thought's topics."""
    if not existing:
        return new
    merged = dict(existing)
    # topics: union by lowercased name; a newer thought about the same topic wins
    by_name = {(t.get("name") or "").lower(): t for t in merged.get("topics", [])}
    for t in new.get("topics", []):
        by_name[(t.get("name") or "").lower()] = t
    merged["topics"] = list(by_name.values())
    # concerns / actionItems / events: append (dedupe concerns by value)
    existing_concerns = set(merged.get("concerns", []))
    for c in new.get("concerns", []):
        if c not in existing_concerns:
            merged.setdefault("concerns", []).append(c)
            existing_concerns.add(c)
    merged["actionItems"] = merged.get("actionItems", []) + new.get("actionItems", [])
    merged["events"] = merged.get("events", []) + new.get("events", [])
    return merged


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
    await ws.accept()
    from app.deepgram_stream import make_live_connection

    loop = asyncio.get_event_loop()
    accumulated: list[str] = []
    sid = str(uuid.uuid4())

    def on_transcript(text: str, is_final: bool):
        if is_final:
            accumulated.append(text)
        live = " ".join(accumulated)
        if not is_final and text:
            live = (live + " " + text).strip()
        asyncio.run_coroutine_threadsafe(
            ws.send_json({"type": "partial", "text": live.strip()}), loop
        )

    def on_utterance_end():
        chunk = " ".join(accumulated).strip()
        if not chunk:
            return
        asyncio.run_coroutine_threadsafe(
            ws.send_json({"type": "partial_final", "text": chunk}), loop
        )

    dg = await make_live_connection(on_transcript, on_utterance_end)

    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                try:
                    dg.send(msg["bytes"])
                except Exception as e:
                    print(f"[ws] dg.send failed: {e}")
                    break
            elif msg.get("text") is not None:
                text = msg["text"]
                try:
                    ctrl = json.loads(text) or {}
                    done = ctrl.get("type") == "done"
                    if isinstance(ctrl.get("graph"), dict):
                        ws_graph = ctrl["graph"]
                    if "request_actions" in ctrl:
                        ws_request_actions = bool(ctrl["request_actions"])
                except Exception:
                    done = text == "done"
                if done:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await dg.finish()
        except Exception as e:
            print(f"[ws] dg.finish failed: {e}")
        full = " ".join(accumulated).strip()
        try:
            if full:
                result = extract_thought(full, existing_topics=[])
                await ws.send_json({"type": "extraction", "data": result})
            await ws.close()
        except Exception as e:
            print(f"[ws] finalize failed: {e}")


@app.post("/extract-thought")
def extract(payload: dict):
    text = (payload.get("text") or payload.get("transcript") or "").strip()
    if not text:
        return {"error": "text is required"}
    existing = payload.get("existing_topics") or []
    graph = payload.get("graph")
    request_actions = bool(payload.get("request_actions"))
    return extract_thought(text, existing, graph=graph, request_actions=request_actions)


@app.post("/summarize-category")
def summarize_category(payload: dict):
    category = (payload.get("category") or "").strip()
    thoughts = [t for t in (payload.get("thoughts") or []) if (t or "").strip()]
    concerns = payload.get("concerns") or []
    actions = payload.get("actions") or []
    events = payload.get("events") or []
    if not thoughts:
        return {"summary": ""}

    from app.llm import claude_configured, chat_claude

    def local_summary() -> str:
        n = len(thoughts)
        parts = [f"{n} thought{'s' if n != 1 else ''} gathered here on {category}."]
        if concerns:
            parts.append("Recurring concerns: " + "; ".join(concerns[:3]) + ".")
        if actions:
            tail = f" and {len(events)} upcoming event{'s' if len(events) != 1 else ''}" if events else ""
            parts.append(f"{len(actions)} open action item{'s' if len(actions) != 1 else ''}{tail}.")
        elif events:
            parts.append(f"{len(events)} upcoming event{'s' if len(events) != 1 else ''}.")
        return " ".join(parts[:3])

    if not claude_configured():
        return {"summary": local_summary(), "source": "local"}

    system = (
        "You write a short overview of one category in a journaling mind-map. "
        "Given the category name and the thoughts filed under it, write 2-3 sentences "
        "(fewer if there is little content) describing the themes, mood, and what's going on. "
        "Write in a warm, plain second/third-person voice. Return ONLY the sentences, no preamble, no markdown."
    )
    lines = [f"Category: {category}", "", "Thoughts:"]
    lines += [f"- {t}" for t in thoughts]
    if concerns:
        lines += ["", "Concerns: " + "; ".join(concerns)]
    if actions:
        lines += ["", "Action items: " + "; ".join(actions)]
    if events:
        lines += ["", "Events: " + "; ".join(events)]
    try:
        text = chat_claude(system, "\n".join(lines), max_tokens=200).strip()
        return {"summary": text or local_summary(), "source": "claude"}
    except Exception as exc:
        return {"summary": local_summary(), "source": "local", "error": str(exc)}


@app.post("/save-session")
def save_session_route(payload: dict):
    session_id = (payload.get("session_id") or "").strip()
    data = payload.get("data")
    if not session_id or not isinstance(data, dict):
        return {"ok": False, "error": "session_id (str) and data (dict) are required"}
    merged = _merge_session(SESSIONS_EXTRACT.get(session_id), data)
    SESSIONS_EXTRACT[session_id] = merged
    try:
        from app.memory import save_session, ensure_index
        ensure_index()
        save_session(session_id, merged)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "session_id": session_id, "topics_indexed": len(merged.get("topics", []))}


@app.post("/classify")
def classify(payload: dict):
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
    from app.suggest import suggest_for_node
    fallback = SESSIONS_EXTRACT.get(req.session_id)
    if fallback is None:
        mem = SESSIONS.get(req.session_id)
        fallback = mem.model_dump() if mem else None
    return suggest_for_node(req.node_id, req.session_id, fallback=fallback, aliases=req.aliases).model_dump()


@app.get("/search")
def search(q: str):
    from app.memory import search_past
    return {"results": search_past(q, k=8)}


# ─────────────────────────── Milestone 3 ───────────────────────────
@app.post("/execute")
async def execute(req: ExecuteRequest):
    session = SESSIONS.get(req.session_id)
    if not session:
        return {"error": "session not found"}
    node = next((n for n in session.nodes if n.id == req.node_id), None)
    if not node:
        return {"error": "node not found"}
    node.status = "running"
    from app.agent_bridge import dispatch_task
    result = await dispatch_task(node)
    node.status = "done" if result.get("ok") else "failed"
    return {"node_id": node.id, "status": node.status, "result": result}


# ─────────────────────────── Google Calendar ────────────────────────
@app.get("/calendar/status")
def calendar_status():
    if not os.path.exists(GOOGLE_TOKEN_PATH):
        return {"connected": False}
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request as GRequest
        creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_PATH, CALENDAR_SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(GRequest())
            with open(GOOGLE_TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
        return {"connected": creds.valid}
    except Exception as e:
        return {"connected": False, "error": str(e)}


@app.get("/calendar/auth")
def calendar_auth():
    if not os.path.exists(GOOGLE_CREDS_PATH):
        return {"error": f"google_credentials.json not found at {GOOGLE_CREDS_PATH}"}
    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_secrets_file(
            GOOGLE_CREDS_PATH,
            scopes=CALENDAR_SCOPES,
            redirect_uri="http://localhost:8000/calendar/callback",
        )
        auth_url, state = flow.authorization_url(prompt="consent", access_type="offline")
        _cal_state["state"] = state
        return RedirectResponse(auth_url)
    except Exception as e:
        return {"error": str(e)}


@app.get("/calendar/callback")
def calendar_callback(code: str, state: str = ""):
    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_secrets_file(
            GOOGLE_CREDS_PATH,
            scopes=CALENDAR_SCOPES,
            redirect_uri="http://localhost:8000/calendar/callback",
            state=_cal_state.get("state"),
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        with open(GOOGLE_TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        return RedirectResponse("http://localhost:5173?calendar=connected")
    except Exception as e:
        return RedirectResponse(f"http://localhost:5173?calendar=error")


@app.post("/calendar/add-event")
def calendar_add_event(payload: dict):
    if not os.path.exists(GOOGLE_TOKEN_PATH):
        return {"ok": False, "error": "Calendar not connected. Visit /calendar/auth first."}
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request as GRequest
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_PATH, CALENDAR_SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(GRequest())
            with open(GOOGLE_TOKEN_PATH, "w") as f:
                f.write(creds.to_json())

        service = build("calendar", "v3", credentials=creds)
        title = payload.get("title", "Thought Galaxy Event")
        datetime_iso = payload.get("datetime")
        duration_min = int(payload.get("duration_min", 60))
        description = payload.get("description", "")

        if datetime_iso:
            start = datetime.datetime.fromisoformat(datetime_iso)
        else:
            start = (datetime.datetime.now() + datetime.timedelta(days=1)).replace(
                hour=10, minute=0, second=0, microsecond=0
            )

        end = start + datetime.timedelta(minutes=duration_min)
        tz = os.environ.get("CALENDAR_TZ", "America/New_York")

        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start.isoformat(), "timeZone": tz},
            "end": {"dateTime": end.isoformat(), "timeZone": tz},
        }
        event = service.events().insert(calendarId="primary", body=body).execute()
        return {"ok": True, "link": event.get("htmlLink"), "title": title}
    except Exception as e:
        return {"ok": False, "error": str(e)}