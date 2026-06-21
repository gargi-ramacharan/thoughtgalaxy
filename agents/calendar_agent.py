"""Milestone 3 — Calendar Agent.

Takes a task node and turns it into a Google Calendar event. Exposed both as a
plain function (handle_calendar_task, called directly by the backend bridge for
a fast/reliable demo path) and as a Fetch.ai uAgent (for the proper
multi-agent story).

Google setup (do once, the night before):
  1. console.cloud.google.com → new project
  2. Enable Google Calendar API
  3. OAuth consent screen → add yourself as a test user
  4. Create OAuth Desktop credentials → download → backend/google_credentials.json
  5. First run opens a browser to authorize; token is cached after.
"""
import os
import datetime
from uagents import Agent, Context, Model


# ─── direct path (backend bridge calls this) ───
def handle_calendar_task(text: str, detail: str) -> dict:
    """Parse a task into an event and create it. Returns {ok, link|error}."""
    try:
        when = _infer_datetime(f"{text} {detail}")
        event = _create_event(summary=text, description=detail, start=when)
        return {"ok": True, "link": event.get("htmlLink"), "when": when.isoformat()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _infer_datetime(text: str) -> datetime.datetime:
    """Very small heuristic. For the demo, let Claude extract the datetime
    during classification and pass it through instead of guessing here.
    Defaults to tomorrow 3pm if nothing is found."""
    now = datetime.datetime.now()
    base = (now + datetime.timedelta(days=1)).replace(
        hour=15, minute=0, second=0, microsecond=0
    )
    return base


def _calendar_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
    creds = None
    token_path = "backend/token_calendar.json"
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            os.environ.get("GOOGLE_CREDENTIALS_PATH", "backend/google_credentials.json"),
            SCOPES,
        )
        creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def _create_event(summary, description, start, duration_min=60):
    service = _calendar_service()
    end = start + datetime.timedelta(minutes=duration_min)
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": "America/Los_Angeles"},
        "end": {"dateTime": end.isoformat(), "timeZone": "America/Los_Angeles"},
    }
    return service.events().insert(calendarId="primary", body=body).execute()


# ─── Fetch.ai agent path ───
class TaskRequest(Model):
    text: str
    detail: str


class TaskResult(Model):
    ok: bool
    info: str


calendar_agent = Agent(
    name="thought_galaxy_calendar",
    seed=os.environ.get("CALENDAR_AGENT_SEED", "calendar-dev-seed"),
    port=8002,
    endpoint=["http://127.0.0.1:8002/submit"],
)


@calendar_agent.on_event("startup")
async def announce(ctx: Context):
    ctx.logger.info(f"Calendar Agent address: {calendar_agent.address}")


@calendar_agent.on_message(model=TaskRequest, replies=TaskResult)
async def on_task(ctx: Context, sender: str, msg: TaskRequest):
    result = handle_calendar_task(msg.text, msg.detail)
    await ctx.send(
        sender,
        TaskResult(ok=result["ok"], info=result.get("link", result.get("error", ""))),
    )


if __name__ == "__main__":
    calendar_agent.run()
