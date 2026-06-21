"""smoke_test.py — proves your whole Milestone 2 stack works end to end.

Run from `backend/`:
    python3 -m app.smoke_test
"""
import os
from dotenv import load_dotenv
load_dotenv()

print("--- checking keys are loaded ---")
for key in ("REDIS_URL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
    print(f"  {key}: {'set' if os.environ.get(key) else 'MISSING'}")
print()

from datetime import datetime, timezone
from .schemas import Session, Node, NodeType
from .memory import ensure_index, save_session, search_past
from .suggest import suggest_for_node

print("1) creating Redis index (safe if it already exists)...")
ensure_index()
print("   ok\n")

session = Session(
    id="demo-session-1",
    created_at=datetime.now(timezone.utc).isoformat(),
    transcript=(
        "I'm so stressed about my exams this week, especially calc. "
        "I really need to start reviewing chapters 6 through 9 before Tuesday."
    ),
    nodes=[
        Node(id="n1", text="Stressed about finals", type=NodeType.EMOTION,
             detail="Three exams in two days, feeling overwhelmed"),
        Node(id="n2", text="Study for calc final", type=NodeType.TASK,
             detail="Review chapters 6-9 before Tuesday", connections=["n1"]),
    ],
)

print("2) saving session + embedding both nodes in Redis...")
save_session(session)
print("   ok\n")

print("3) semantic search — query doesn't share words with the stored text:")
results = search_past("feeling overwhelmed about school", k=3)
for r_ in results:
    print(f"   [{r_['score']:.3f}] ({r_['type']}) {r_['text']}")
if not results:
    print("   (still nothing — paste this output back, we'll dig further)")
print()

print("4) asking the Insight flow for a grounded suggestion on the task node...")
suggestion = suggest_for_node("n2", "demo-session-1")
print(f"   {suggestion.text}")
print(f"   drawn from: {suggestion.drawn_from}\n")

print("Done. If step 3 found a real match, your whole Redis vector search works.")