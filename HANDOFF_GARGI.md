# Handoff → Gargi (backend) — guidance / memory fixes

**From:** Linda (frontend)
**Re:** `/save-session` + `/suggest` (Milestone 2 memory + "what should I do?" guidance)
**Status:** Frontend is done and wired. Two backend bugs remain that make guidance look broken in the demo. Both are in your files.

This doc is written so your Claude can implement it cold — exact files, line numbers, current code, and target code are below.

---

## Context (how the feature flows)

1. On page load the frontend mints one `SESSION_ID` (one per page load, NOT per thought — this is deliberate; `/suggest` excludes the current session when searching past memory).
2. Every time the user commits a thought (text "add to galaxy" **and** the voice path), the frontend fires `POST /save-session {session_id, data}` where `data` is the extraction output `{title, summary, topics[], concerns[], actionItems[], events[]}`.
3. When the user dives into a top-level bubble and taps **"what should I do?"**, the frontend fires `POST /suggest {node_id, aliases, session_id}` and renders `res.text` + `res.drawn_from`.

The frontend side of all three steps is complete and tested. The response shape `/suggest` returns (`Suggestion{node_id, text, drawn_from}`) already matches what the frontend reads. **Don't change the response shape.**

---

## ✅ Already done by Linda (frontend) — no action needed, just FYI

- `SESSION_ID` generated once per page load (index.html ~line 802).
- `saveSessionToBackend()` helper + calls in both commit paths (`rok` handler ~1241, WS voice path ~1340).
- "what should I do?" button in `openNotes` (top-level bubbles only — see note at the very bottom).
- **Dark-mode fix** for the guidance result text.
- **Frontend half of Bug #2:** the `/suggest` body now sends an `aliases` array — every prior name the tapped bubble has been known by (handles multi-hop rename chains). This is currently **inert** until you do the backend half below.

---

## 🐞 Bug #1 — the session only ever stores the LAST committed thought (HIGH PRIORITY)

**Symptom:** Within one page load, "what should I do?" only works on bubbles from the *most recent* thought. Tap a bubble created by an earlier thought in the same session and you get **"I couldn't find that thought."**

**Root cause:** both stores overwrite instead of accumulating.

- `app/main.py:228` — `SESSIONS_EXTRACT[session_id] = data` (overwrites)
- `app/memory.py` `save_session()` — `r.set(f"session:{session_id}", json.dumps(data))` (overwrites the blob `get_session` reads)

So `get_session(session_id)` returns only the last thought, and `suggest.py` looks up the tapped topic in *that one thought's* `topics[]` (suggest.py:65) → miss.

(Note: the *embedding index* already accumulates correctly — records are keyed `{session_id}::{name}` — so cross-session semantic recall is fine. It's only the current-session map lookup that's truncated.)

### Fix — merge new topics into the existing session, in `app/main.py`

Add a merge helper near the top of main.py:

```python
def _merge_session(existing: dict | None, new: dict) -> dict:
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
    # concerns / actionItems / events: append
    for key in ("concerns", "actionItems", "events"):
        merged[key] = (existing.get(key) or []) + (new.get(key) or [])
    # keep the latest title/summary
    merged["title"] = new.get("title") or existing.get("title")
    merged["summary"] = new.get("summary") or existing.get("summary")
    return merged
```

Then in `save_session_route` (main.py:218), accumulate before storing:

```python
    session_id = (payload.get("session_id") or "").strip()
    data = payload.get("data")
    if not session_id or not isinstance(data, dict):
        return {"ok": False, "error": "session_id (str) and data (dict) are required"}
    merged = _merge_session(SESSIONS_EXTRACT.get(session_id), data)   # <-- accumulate
    SESSIONS_EXTRACT[session_id] = merged                            # <-- store merged
    try:
        from app.memory import save_session, ensure_index
        ensure_index()
        save_session(session_id, merged)                            # <-- save merged blob
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "session_id": session_id, "topics_indexed": len(merged.get("topics", []))}
```

Doing the merge here means `memory.save_session` stores the full accumulated blob (so `get_session` returns everything) and re-indexes all topic embeddings each commit (idempotent — same `{session_id}::{name}` ids overwrite). **No change needed inside memory.py** with this approach.

---

## 🐞 Bug #2 — renamed/merged bubbles don't match (MEDIUM — do after #1)

**Symptom:** A bubble created as "romantic interest" then renamed to "josh" is tapped as `josh`, but the thought that created it stored the topic under `romantic interest`. `/suggest` does an exact `tp.get("name") == node_id` match (suggest.py:65) → miss → "I couldn't find that thought." Also fails if Claude ever emits a non-lowercase topic name.

**Frontend is already sending the fix:** the `/suggest` body now includes `aliases: [...]` — all the historical names that resolve to the tapped bubble. You just need to consume it.

### 3 small backend changes

**a) `app/schemas.py:37` — add the field to `SuggestRequest`:**

```python
class SuggestRequest(BaseModel):
    """Milestone 2 — user taps a bubble and asks for guidance."""
    node_id: str
    session_id: str
    aliases: list[str] = []      # <-- add this (prior names of the tapped bubble)
```

**b) `app/main.py:262` — pass it through:**

```python
    return suggest_for_node(
        req.node_id, req.session_id, aliases=req.aliases, fallback=fallback
    ).model_dump()
```

**c) `app/suggest.py:55` — accept aliases and match case-insensitively against name OR any alias:**

```python
def suggest_for_node(node_id: str, session_id: str, aliases=None, fallback=None) -> Suggestion:
    ...
    topics = session.get("topics", [])
    names = {node_id.lower(), *((a or "").lower() for a in (aliases or []))}
    tapped = next((tp for tp in topics if (tp.get("name") or "").lower() in names), None)
    if not tapped:
        return Suggestion(node_id=node_id, text="I couldn't find that thought.")
```

Bug #1 and Bug #2 work together: even if the accumulated blob still holds a topic under its *old* name (the merge in #1 unions by name and doesn't replay renames), the alias match in #2 still finds it.

---

## 🧪 Test plan

1. Hard refresh, DevTools → Network. Add a thought → "add to galaxy". Confirm `POST /save-session` → 200.
2. Add a **second, different** thought and commit it. Then dive into a bubble from the **first** thought and tap "what should I do?" — before the fix this said "I couldn't find that thought"; after Bug #1 it should return a real suggestion. *(First time in a fresh session, the "drew on past sessions" line may be empty — that's correct, `/suggest` excludes the current session.)*
3. Rename a bubble (e.g. let a generic hub get renamed when a proper name appears), then tap its guidance button. After Bug #2 it should still resolve. Confirm `aliases` is populated in the request payload.
4. Reload (mints a new `SESSION_ID`), add a thought on a similar theme, tap the same topic — now you should see a real suggestion **with** a "drew on past sessions" line. This two-reload step is the only way to see recall locally.
5. Confirm the button still renders for topics with zero past data / zero notes — don't let an empty state throw mid-demo.

---

## Out of scope (don't do unless asked)

- **Guidance on sub-bubbles.** `/suggest` matches top-level `session.topics[].name`; subtopics are namespaced `parent▸sub` (the `SUBSEP` separator), so they'd silently miss. The frontend intentionally only shows the button on top-level hubs. If we want sub-bubble guidance later, that's an additional `suggest.py` change (resolve subtopic keys) — flag it, don't build it now.
- **Don't change the `/suggest` response shape** (`{node_id, text, drawn_from}`) — the frontend depends on it.
