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


def _format_map(graph: dict[str, Any] | None, existing_topics: list[str]) -> str:
    """Render the user's CURRENT mind-map (hubs + their subtopics + aliases) so the
    model can reconcile a new thought against what already exists."""
    nodes = graph.get("nodes") if isinstance(graph, dict) else None
    if not nodes:
        existing = ", ".join(existing_topics) if existing_topics else "(none yet)"
        return f"(no map yet; existing topic names: {existing})"
    lines: list[str] = []
    for nd in nodes:
        name = (nd.get("name") or "").strip()
        if not name:
            continue
        aliases = [a for a in (nd.get("aliases") or []) if a]
        contribution = (nd.get("contribution") or "").strip()
        line = f'- "{name}"'
        if aliases:
            line += f' (also known as: {", ".join(aliases)})'
        if contribution:
            line += f" — {contribution}"
        lines.append(line)
        for st in (nd.get("subtopics") or []):
            sn = (st.get("name") or "").strip()
            if not sn:
                continue
            sc = (st.get("contribution") or "").strip()
            lines.append(f'    • "{sn}"' + (f" — {sc}" if sc else ""))
    return "\n".join(lines) if lines else "(no map yet)"


def _system_prompt(existing_topics: list[str], graph: dict[str, Any] | None = None,
                   request_actions: bool = False,
                   existing_subtopics: dict | None = None) -> str:
    import datetime
    today = datetime.date.today().strftime("%A, %B %d, %Y")
    current_map = _format_map(graph, existing_topics)
    if request_actions:
        action_rule = (
            "- actionItems: ALWAYS propose concrete, helpful next steps you could take, "
            "even if the text does not explicitly state a task. Infer 1-4 useful, specific, actionable "
            "suggestions grounded in what you wrote (e.g. 'text Josh to ask if he's free Saturday'). "
            "Still include any tasks you explicitly mentioned. Each actionItem's 'topic' is the related topic name."
        )
    else:
        action_rule = (
            "- Only include actionItems when genuinely implied by the text (you mention a task you "
            "could/should do). Do NOT invent action items for plain reflections — return an empty array then."
        )

    # Topic-count guidance flips entirely depending on whether the user started
    # from a template. With existing sections present, those sections are
    # CONTAINERS and we file everything inside them (no 3-4 topic splitting).
    # Blank start → natural extraction with the usual 3-4 topic spread.
    if existing_topics:
        existing = ", ".join(existing_topics)
        topics_rule = f"""TEMPLATE MODE — existing sections are CONTAINERS, not peers.
The existing sections are: {existing}
These are broad life areas. Every specific thing the person mentions belongs INSIDE the closest container.
Rules:
- "violin", "guitar", "painting" → hobbies
- "CS midterm", "homework", "exam", "studying" → school
- "running", "cross country", "gym", "working out" → health
- "mom", "dad", "sister" → family
- A specific activity or task ALWAYS files under its closest container.
- NEVER create a new topic if an existing container could hold it.
- Only create a new topic (status "new") when something genuinely has NO existing container.
- Return at most 1 new topic per entry. Aim for 0.
- Do NOT create separate topics for each activity mentioned. Group them."""
        reconcile_reuse = (
            "- Set status 'existing' and reuse the EXACT existing container name when a topic fits "
            "one of the existing sections (see TEMPLATE MODE above). Default to filing inside a container; "
            "only use status 'new' for something with no possible container."
        )
    else:
        topics_rule = """- AIM FOR 3-4 TOPICS whenever the entry has enough substance to support them. If you wrote or said several sentences about ONE subject, break its distinct facets into SEPARATE top-level topics (each becomes its own bubble), and link them with 'connects' — a richer spread of bubbles gets far more out of the visualization than one bubble with everything buried inside it. Example: a few sentences about someone you're seeing should become topics like "elliot jang", "what draws me to him", "red flags & harm", and "staying guarded" — NOT a single "elliot jang" topic with those buried as subtopics. The central subject (e.g. the person) is one topic; each major angle you reflect on becomes its own connected topic.
- BUT never manufacture topics out of thin air — only split when the text genuinely contains distinct facets. Let the NUMBER OF TOPICS SCALE WITH THE LENGTH AND RICHNESS of the entry, with no fixed upper limit: a single short idea like "matcha tastes good" = 1 topic; "I have a CS midterm and I'm stressed about it" = 1 topic (one coherent worry); 2-3 sentences touching distinct angles = 2-3 topics; a few sentences with several distinct facets = 3-4 topics; a long, multi-paragraph entry that genuinely covers many distinct facets can have 5, 6, or more topics. The longer and more wide-ranging the text, the more bubbles it should produce — just make sure every topic corresponds to something actually distinct in the text, never filler.
- When in doubt between burying a substantial facet as a subtopic vs. promoting it to its own top-level topic, PROMOTE it."""
        reconcile_reuse = (
            "- Set status 'existing' and reuse the EXACT existing name when a topic is clearly one already on the map.\n"
            "- When the CURRENT MAP lists NO existing sections (the user started blank), do NOT force anything — "
            "extract topics naturally per the rules above, creating them as 'new'."
        )
    if existing_subtopics:
        lines = []
        for parent, subs in existing_subtopics.items():
            if subs:
                lines.append(f"- {parent}: {', '.join(subs)}")
        subtopic_block = (
            "\nSUBTOPIC RECONCILIATION — each container has its own existing sub-bubbles.\n"
            "Inside each top-level container, these sub-bubbles already exist:\n"
            + "\n".join(lines) + "\n"
            "Rules:\n"
            "- When a thought files into a container, REUSE the closest existing sub-bubble name.\n"
            '- "CS midterm", "final exam", "quiz" → school\'s "exams" sub-bubble\n'
            '- "violin", "guitar", "piano" → hobbies\'s "music" sub-bubble\n'
            '- "running", "gym", "lifting" → health\'s "exercise" sub-bubble\n'
            "- Only create a NEW sub-bubble inside a container when absolutely no existing one fits.\n"
            "- NEVER output a sub-bubble name that already exists in that container — use merge reconcile instead.\n"
        ) if lines else ""
    else:
        subtopic_block = ""

    return f"""You extract structure from a person's short journal or voice-note text for a mind-map journaling app, AND reconcile it against the map they have built so far. Return ONLY a JSON object and nothing else (no prose, no markdown fences).

VOICE — IMPORTANT: every piece of human-readable text you generate (title, summary, each topic/subtopic 'contribution', concerns, actionItems) must address the writer directly as "you"/"your". NEVER refer to the writer in the third person — do NOT write "the user", "the person", "they", "she", or "he". E.g. write "you're stressed about your CS midterm", not "the user is stressed about their CS midterm".

Today is {today}. Use this to resolve relative dates like "next Friday", "tomorrow", "this weekend", "Tuesday 3-4pm".

CURRENT MAP (the user's existing hubs, their subtopics indented underneath, and any known aliases):
{current_map}

Schema:
{{"title":string,"summary":string,"topics":[{{"name":string,"status":"new"|"existing","kind":"topic"|"person"|"place","weight":number,"connects":[string],"contribution":string,"excerpts":[string],"reconcile":{{"action":"none"|"rename"|"merge","target":string}},"subtopics":[{{"name":string,"contribution":string,"excerpts":[string],"reconcile":{{"action":"none"|"merge","target":string}}}}]}}],"concerns":[string],"actionItems":[{{"text":string,"topic":string}}],"events":[{{"title":string,"date":string,"datetime":string,"duration_min":number,"topic":string}}]}}
Rules:
- title is a short (3-6 word) human-friendly headline for THIS whole entry.
- topics are the main ideas / areas of life mentioned. Names are short and lowercase.
{topics_rule}
- weight is 1-5: how central/important this topic is in THIS entry.
- 'connects' lists other topic names from this same response that are related.
- 'contribution' is ONE short sentence on how this entry relates to / contributes to this topic.
- 'excerpts' is 1-3 SHORT verbatim substrings copied EXACTLY, character-for-character, from the input text that pertain to this topic. Do NOT paraphrase, reword, fix typos, or change casing — copy exact spans so they can be located in the original. If nothing maps cleanly, return an empty array.
- 'subtopics' are for FINER-GRAINED detail nested under a top-level topic, used sparingly. Prefer promoting a substantial facet to its OWN top-level topic (see the 3-4 topics rule above); reserve subtopics for small details that clearly belong inside a single topic and aren't worth their own bubble (e.g. topic 'school' -> subtopic 'that one professor'). Names are short and lowercase. Each subtopic has its own 'contribution' (ONE short sentence on how this entry relates to that facet) and 'excerpts' (1-3 SHORT verbatim substrings, same exact-copy rule as above). For a simple thought with nothing to break out, return an EMPTY subtopics array — do NOT invent facets.

RECONCILIATION (compare each topic to the CURRENT MAP above and decide how it fits):
{reconcile_reuse}
- RENAME (do this EAGERLY): the moment this entry reveals a more specific or proper name for something that already exists on the map as a vaguer/generic hub, RENAME the hub. Output the topic under the NEW proper name and set its reconcile to {{"action":"rename","target":"<OLD existing name>"}}. Renaming is LOW-RISK and REVERSIBLE — the old name is automatically kept as an alias, so nothing is lost. When in doubt, PREFER to rename rather than create a new topic or add a subtopic. A named person/place/thing that is plainly the subject of an existing generic hub MUST rename that hub — never add them as a separate topic or as a subtopic of the generic hub.
  Worked example: CURRENT MAP has a hub "romantic interest". New entry says "his name is Josh and I think he likes me too." Correct output: a topic with name "josh", reconcile {{"action":"rename","target":"romantic interest"}}. WRONG: making "josh" a new separate topic, or a subtopic of "romantic interest", or leaving the hub named "romantic interest".
  Generic hubs that should be renamed as soon as a proper name appears include things like: "romantic interest", "crush", "this person", "the guy/girl", "my friend", "someone", "a place", "the trip", "my job", "work thing", "the project". If the entry names them, rename.
- MERGE: if a topic means essentially the same as an existing hub but you would phrase it differently, set reconcile to {{"action":"merge","target":"<existing hub name>"}} so it folds in instead of creating a near-duplicate.
- Otherwise set reconcile to {{"action":"none"}} (or omit it).
- SUBTOPIC DEDUP: do NOT create a subtopic that substantially overlaps an existing sibling subtopic shown in the CURRENT MAP. If a facet is essentially the same as an existing sibling, set that subtopic's reconcile to {{"action":"merge","target":"<existing sibling name>"}}. Prefer a few distinct subtopics over many overlapping ones (e.g. do NOT make 'timing & feasibility', 'timing & access', and 'timing & hesitation' separate siblings — they are one facet about timing).
{subtopic_block}{action_rule}
- Only include events when genuinely implied. Many plain reflections have NONE — return an empty array then; never invent them.
- events have a time/date (deadlines, appointments, trips). actionItems are tasks you could do.
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

    # Per-topic excerpts (exact sentences mentioning the topic) + a contribution line.
    for t in topics:
        name = t["name"]
        matches = [s for s in sentences if _mentions(s, name)]
        t["excerpts"] = matches[:2]
        t["contribution"] = (
            f"This entry mentions {name}." if matches else f"This entry relates to {name}."
        )
        # offline heuristic can't reliably break a topic into facets — leave the inner world empty.
        t["subtopics"] = []

    # Short headline from the summary.
    title_words = summary.split()
    title = " ".join(title_words[:6]) + ("…" if len(title_words) > 6 else "")

    return {
        "title": title or "untitled thought",
        "summary": summary,
        "topics": topics,
        "concerns": concerns[:4],
        "actionItems": action_items[:6],
        "events": events[:6],
        "source": "local",
        "model": "offline rules",
    }


def extract_thought(
    text: str,
    existing_topics: list[str] | None = None,
    graph: dict[str, Any] | None = None,
    request_actions: bool = False,
    existing_subtopics: dict | None = None,
) -> dict[str, Any]:
    """Claude (graph-aware reconciliation) → local rules.

    `graph` is the frontend's current map snapshot: {"nodes":[{name, kind,
    contribution, aliases:[...], subtopics:[{name, contribution}]}]}. When present
    it lets Claude rename/merge against what already exists. The local fallback
    ignores it — it cannot reconcile and just emits dumb topics as before.
    """
    existing = existing_topics or []
    # if a graph snapshot is given, derive existing_topics from it for the fallback path
    if graph and isinstance(graph, dict) and not existing:
        existing = [n.get("name", "") for n in (graph.get("nodes") or []) if n.get("name")]
    try:
        data, source, model = chat_json(
            _system_prompt(existing, graph, request_actions, existing_subtopics), text, max_tokens=1500
        )
        data["source"] = source
        data["model"] = model
        return data
    except Exception as exc:
        data = extract_local(text, existing)
        data["fallback_reason"] = str(exc)
        return data
