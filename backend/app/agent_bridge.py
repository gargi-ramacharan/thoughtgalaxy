"""Milestone 3 — bridge between FastAPI and the Fetch.ai agents.

The backend doesn't execute calendar/email itself; it hands a task node to the
right uAgent and waits for the reply. Fetch.ai's uAgents communicate over their
own protocol, so this module is the thin adapter that translates a Node into an
agent message and back.

For the hackathon you have two integration styles — pick based on time:

  A) Direct (fast): import the agent's handler function and call it. Works,
     but doesn't show off Fetch.ai's messaging. Fine for a backup demo.

  B) Proper uAgents messaging (what judges want to see): send a typed message
     to the agent's address on the local bureau / Agentverse and await its
     response. Use this if the Fetch.ai integration is working.

This file ships with (A) wired and (B) sketched, so you have a working path
immediately and can upgrade in place.
"""
import os
from app.schemas import Node

# ─── Style B address book (fill from `python agents/*.py` startup logs) ───
CALENDAR_AGENT_ADDRESS = os.environ.get("CALENDAR_AGENT_ADDRESS", "")
EMAIL_AGENT_ADDRESS = os.environ.get("EMAIL_AGENT_ADDRESS", "")


async def dispatch_task(node: Node) -> dict:
    """Send a task node to the appropriate agent, return its result."""
    # Decide which agent: a crude keyword router. In practice let Claude tag
    # the node with an "action" field during classification (calendar|email).
    text = f"{node.text} {node.detail}".lower()
    is_email = any(w in text for w in ("email", "message", "reach out", "tell", "ask"))

    try:
        if is_email:
            from agents.email_agent import handle_email_task
            return handle_email_task(node.text, node.detail)
        else:
            from agents.calendar_agent import handle_calendar_task
            return handle_calendar_task(node.text, node.detail)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # ── Style B sketch (uAgents messaging) ──
    # from uagents.query import query
    # from agents.messages import TaskRequest
    # addr = EMAIL_AGENT_ADDRESS if is_email else CALENDAR_AGENT_ADDRESS
    # reply = await query(addr, TaskRequest(text=node.text, detail=node.detail))
    # return reply.decode_payload()
