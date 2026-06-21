"""Milestone 3 — Email Agent.

Takes a task node like "email professor about extension" and drafts the email.

IMPORTANT design choice: this agent DRAFTS and returns the email for the user
to review. It does not auto-send. Sending on someone's behalf without a final
look is exactly the kind of irreversible action that goes wrong on a demo
stage and in real life — show the draft, let the human hit send. You can wire
true send via the Gmail API once you trust it, behind an explicit confirm.

Gmail setup mirrors the calendar agent: enable Gmail API, OAuth desktop creds,
scope gmail.compose (draft) — NOT gmail.send until you add a confirm step.
"""
import os
import base64
from email.mime.text import MIMEText
from uagents import Agent, Context, Model


def handle_email_task(text: str, detail: str) -> dict:
    """Draft an email with Claude, create a Gmail draft, return it for review."""
    try:
        draft = _draft_with_claude(text, detail)
        gmail_draft = _create_gmail_draft(draft["to"], draft["subject"], draft["body"])
        return {
            "ok": True,
            "mode": "draft",
            "subject": draft["subject"],
            "body": draft["body"],
            "to": draft["to"],
            "draft_id": gmail_draft.get("id"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _draft_with_claude(text: str, detail: str) -> dict:
    from anthropic import Anthropic
    import json

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
    msg = client.messages.create(
        model=model, max_tokens=600,
        messages=[{
            "role": "user",
            "content": f"""Draft a short, polite email for this task. Return ONLY \
JSON: {{"to":"", "subject":"", "body":""}}. Leave "to" blank if unknown.

Task: {text}
Context: {detail}""",
        }],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].replace("json", "", 1).strip()
    return json.loads(raw)


def _gmail_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
    creds = None
    token_path = "backend/token_gmail.json"
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
    return build("gmail", "v1", credentials=creds)


def _create_gmail_draft(to: str, subject: str, body: str) -> dict:
    service = _gmail_service()
    mime = MIMEText(body)
    if to:
        mime["to"] = to
    mime["subject"] = subject
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    return service.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()


# ─── Fetch.ai agent path ───
class TaskRequest(Model):
    text: str
    detail: str


class TaskResult(Model):
    ok: bool
    info: str


email_agent = Agent(
    name="thought_galaxy_email",
    seed=os.environ.get("EMAIL_AGENT_SEED", "email-dev-seed"),
    port=8003,
    endpoint=["http://127.0.0.1:8003/submit"],
)


@email_agent.on_event("startup")
async def announce(ctx: Context):
    ctx.logger.info(f"Email Agent address: {email_agent.address}")


@email_agent.on_message(model=TaskRequest, replies=TaskResult)
async def on_task(ctx: Context, sender: str, msg: TaskRequest):
    result = handle_email_task(msg.text, msg.detail)
    info = result.get("subject", result.get("error", "")) if result["ok"] else result.get("error", "")
    await ctx.send(sender, TaskResult(ok=result["ok"], info=info))


if __name__ == "__main__":
    email_agent.run()
