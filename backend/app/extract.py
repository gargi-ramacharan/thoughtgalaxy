"""Extract mind-map structure from a journal note.

Primary path: Claude (when ANTHROPIC_API_KEY is set and credits remain).
Fallback: local heuristic parser — no API key, no quota, works offline.
"""
from __future__ import annotations

import re
from typing import Any

from .llm import chat_json

DAYS = (
    "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "tomorrow", "today", "tonight",
)
CONCERN_WORDS = (
    "stressed", "stress", "worried", "worry", "anxious", "anxiety",
    "overwhelmed", "overwhelm", "tired", "exhausted", "burned out",
    "scared", "nervous", "behind", "panic", "frustrated", "upset",
    "can't sleep", "not packed", "running late", "deadline",
)
ACTION_PATTERNS = (
    r"\b(?:need to|have to|must|should|gotta|got to|remember to)\s+([^,.;!?]+)",
    r"\b(?:submit|finish|complete|pack|call|email|text|study|review|prepare)\s+([^,.;!?]*)",
)
EVENT_PATTERNS = (
    r"(?P<title>[^,.;!?]{3,60}?)\s+(?:due|by|on|this|next)\s+(?P<date>monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|today|tonight|\d{1,2}/\d{1,2})",
    r"(?P<title>interview|exam|midterm|final|flight|trip|meeting|appointment|project|deadline|presentation)[^,.;!?]*\s+(?P<date>monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|today|tonight|\d{1,2}/\d{1,2})",
    r"(?P<date>monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|today|tonight|\d{1,2}/\d{1,2})[^,.;!?]*\s+(?P<title>interview|exam|flight|trip|meeting|appointment|project|deadline|presentation)",
)
TOPIC_HINTS = (
    "school", "work", "friends", "family", "health", "sleep", "hobbies",
    "project", "homework", "exam", "midterm", "interview", "travel", "trip",
    "flight", "packing", "deadline", "meeting", "study", "class", "job",
    "relationship", "money", "fitness", "music", "creativity",
)
PERSON_RE = re.compile(r"\b([A-Z][a-z]{2,})\b")
PLACE_WORDS = ("airport", "flight", "trip", "travel", "hotel", "campus", "office")


def _system_prompt(existing_topics: list[str]) -> str:
    import datetime
    today = datetime.date.today().strftime("%A, %B %d, %Y")
    existing = ", ".join(existing_topics) if existing_topics else "(none yet)"
    return f"""You extract structure from a person's short journal or voice-note text for a mind-map journaling app. Return ONLY a JSON object and nothing else (no prose, no markdown fences).

Today is {today}. Use this to resolve relative dates like "next Friday", "tomorrow", "this weekend", "Tuesday 3-4pm".

Schema:
{{"summary":string,"topics":[{{"name":string,"status":"new"|"existing","kind":"topic"|"person"|"place","weight":number,"connects":[string]}}],"concerns":[string],"actionItems":[{{"text":string,"topic":string}}],"events":[{{"title":string,"date":string,"datetime":string,"duration_min":number,"topic":string}}]}}
Rules:
- topics are the main ideas / areas of life mentioned. Names are short and lowercase.
- weight is 1-5: how central/important this topic is in THIS entry.
- Reuse these EXISTING topics when they fit (status 'existing'); otherwise 'new': {existing}.
- 'connects' lists other topic names from this same response that are related.
- Only include actionItems and events when genuinely implied. Many plain reflections have NONE — return empty arrays then; never invent them.
- events have a time/date (deadlines, appointments, trips). actionItems are tasks the person could do.
- 'kind' is person for named people, place for locations/trips, else topic.
- For events: 'date' is human-readable (e.g. "Friday June 27"), 'datetime' is ISO 8601 (e.g. "2026-06-27T15:00:00"). For a range like "3-4pm" set duration_min=60 and datetime to start. Default time 10:00 if none given. duration_min defaults to 60."""


def _mentions(text: str, term: str) -> int:
    return len(re.findall(rf"\b{re.escape(term)}\b", text, flags=re.I))


def _first_topic(topics: list[dict[str, Any]]) -> str | None:
    return topics[0]["name"] if topics else None


def extract_local(text: str, existing_topics: list[str]) -> dict[str, Any]:
    """Rule-based extraction — unlimited, no external API."""
    lower = text.lower()
    sentences = [s.strip() for s in re.split(r"[.!?;\n]+", text) if s.strip()]
    if not sentences:
        sentences = [text.strip()]

    topic_map: dict[str, dict[str, Any]] = {}

    def add_topic(name: str, *, kind: str = "topic", weight: int = 2) -> None:
        key = name.lower().strip()
        if not key or len(key) > 40:
            return
        status = "existing" if key in {t.lower() for t in existing_topics} else "new"
        if key in topic_map:
            topic_map[key]["weight"] = min(5, topic_map[key]["weight"] + weight)
            if status == "existing":
                topic_map[key]["status"] = "existing"
            return
        topic_map[key] = {
            "name": key,
            "status": status,
            "kind": kind,
            "weight": min(5, max(1, weight)),
            "connects": [],
        }

    for existing in existing_topics:
        if _mentions(lower, existing):
            add_topic(existing, weight=3)

    for hint in TOPIC_HINTS:
        if _mentions(lower, hint):
            add_topic(hint, weight=2)

    for match in PERSON_RE.finditer(text):
        name = match.group(1).lower()
        if name not in {"i", "im", "i'm", "the", "and", "but", "so", "just"}:
            add_topic(name, kind="person", weight=2)

    for word in PLACE_WORDS:
        if _mentions(lower, word):
            add_topic(word, kind="place", weight=2)

    if not topic_map:
        add_topic("thoughts", weight=3)

    # Co-occurring topics in the same sentence become connects.
    for sentence in sentences:
        sent_lower = sentence.lower()
        present = [k for k in topic_map if _mentions(sent_lower, k)]
        for i, a in enumerate(present):
            for b in present[i + 1 :]:
                if b not in topic_map[a]["connects"]:
                    topic_map[a]["connects"].append(b)
                if a not in topic_map[b]["connects"]:
                    topic_map[b]["connects"].append(a)

    concerns: list[str] = []
    for sentence in sentences:
        sent_lower = sentence.lower()
        if any(word in sent_lower for word in CONCERN_WORDS):
            concerns.append(sentence.strip())

    action_items: list[dict[str, str]] = []
    for pattern in ACTION_PATTERNS:
        for match in re.finditer(pattern, lower, flags=re.I):
            phrase = match.group(0).strip(" .,!?:;")
            if len(phrase) < 8:
                continue
            topic = next(
                (k for k in topic_map if _mentions(match.group(0), k)),
                _first_topic(list(topic_map.values())),
            )
            if topic and not any(a["text"] == phrase for a in action_items):
                action_items.append({"text": phrase, "topic": topic or "thoughts"})

    events: list[dict[str, str]] = []
    for pattern in EVENT_PATTERNS:
        for match in re.finditer(pattern, lower, flags=re.I):
            title = (match.groupdict().get("title") or "event").strip()
            date = (match.groupdict().get("date") or "").strip()
            if not date:
                continue
            title = re.sub(r"\s+", " ", title)
            topic = next(
                (k for k in topic_map if k in title or _mentions(lower, k)),
                _first_topic(list(topic_map.values())),
            )
            event = {"title": title[:60], "date": date, "topic": topic or "thoughts"}
            if event not in events:
                events.append(event)

    # Simple summary from the first sentence or a trimmed version of the text.
    summary = sentences[0]
    if len(summary) > 140:
        summary = summary[:137].rstrip() + "…"

    topics = sorted(topic_map.values(), key=lambda t: t["weight"], reverse=True)
    return {
        "summary": summary,
        "topics": topics,
        "concerns": concerns[:4],
        "actionItems": action_items[:6],
        "events": events[:6],
        "source": "local",
        "model": "offline rules",
    }


def extract_thought(text: str, existing_topics: list[str] | None = None) -> dict[str, Any]:
    """Claude → local rules."""
    existing = existing_topics or []
    try:
        data, source, model = chat_json(_system_prompt(existing), text, max_tokens=1000)
        data["source"] = source
        data["model"] = model
        return data
    except Exception as exc:
        data = extract_local(text, existing)
        data["fallback_reason"] = str(exc)
        return data
