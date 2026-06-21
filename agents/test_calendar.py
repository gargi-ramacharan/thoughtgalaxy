"""test_calendar.py — quick test for the calendar agent's direct path.

IMPORTANT: run this from the REPO ROOT (the folder that contains both
`backend/` and `agents/` as siblings), not from inside agents/ or backend/:

    python3 -m agents.test_calendar

First run will pop open a browser window asking you to log in and authorize —
say yes. After that, it caches a token in backend/token_calendar.json and
won't ask again.
"""
from dotenv import load_dotenv
load_dotenv("backend/.env")  # .env lives in backend/, explicit path needed

from agents.calendar_agent import handle_calendar_task

result = handle_calendar_task(
    text="Study for calc final",
    detail="Review chapters 6-9 before Tuesday",
)

print(result)
if result.get("ok"):
    print(f"\n✅ Event created! Check your Google Calendar, or open: {result['link']}")
else:
    print(f"\n❌ Failed: {result.get('error')}")