# Thought Galaxy 🌌

Voice-first thought mapping. You talk through your day — your stresses, your tasks, your half-formed ideas — and watch them organize themselves into a living constellation. Ask any bubble for guidance and an agent pulls from everything you've said before to suggest a real next step. When you're ready, it can go execute the tasks for you.

Built for UC Berkeley AI Hackathon 2026.

---

## The three milestones

This repo is structured so you can ship at any of three stopping points. Each one is a complete, demoable product on its own.

**Milestone 1 — The Map.** Speak → live transcription → thoughts classified into task / emotion / idea → animated bubble constellation with connections drawn between related thoughts. Sessions persist. This is the wow moment and it stands alone.

**Milestone 2 — The Guidance.** Tap any bubble and ask "what should I do?" An agent pulls semantically related moments from your past sessions and suggests a concrete, grounded next step. Only runs when you ask — it never nags.

**Milestone 3 — The Action.** Task bubbles get an Execute button. Specialized agents add events to your calendar or draft emails. The bubble turns green when done. This is last because it's riskiest; everything above it already wins.

---

## Architecture

```
                    ┌─────────────┐
   speak ──────────▶│  Deepgram   │  streaming speech-to-text
                    └──────┬──────┘
                           │ transcript
                    ┌──────▼──────┐
                    │   Claude    │  classify → {task|emotion|idea}
                    │ (Anthropic) │  + find connections
                    └──────┬──────┘
                           │ JSON nodes
        ┌──────────────────┼──────────────────┐
        │                  │                  │
  ┌─────▼─────┐     ┌──────▼──────┐    ┌──────▼──────┐
  │  Canvas   │     │    Redis    │    │   Fetch.ai  │
  │ (D3 bubble│     │ vector mem  │    │   agents    │
  │  galaxy)  │     │  + search   │    │ (uAgents)   │
  └───────────┘     └─────────────┘    └──────┬──────┘
                                              │
                              ┌───────────────┼───────────────┐
                        ┌─────▼─────┐  ┌──────▼─────┐  ┌──────▼─────┐
                        │  Insight  │  │  Calendar  │  │   Email    │
                        │   Agent   │  │   Agent    │  │   Agent    │
                        │ (M2)      │  │ (M3)       │  │ (M3)       │
                        └───────────┘  └─────┬──────┘  └─────┬──────┘
                                       Google Cal API   Gmail API

  Arize logs every Claude classification · Sentry watches everything
```

## Tech stack & who does what

| Layer | Tool | Role | Milestone |
|---|---|---|---|
| Voice | **Deepgram** | streaming STT, words appear as you speak | 1 |
| Reasoning | **Claude (Anthropic)** | classify thoughts, find connections, suggestions | 1, 2 |
| Canvas | **React + D3** | force-directed bubble galaxy | 1 |
| Memory | **Redis** | vector search over past sessions, agent memory | 2 |
| Orchestration | **Fetch.ai (uAgents)** | route bubbles to the right agent, run in parallel | 2, 3 |
| Execution | **Google Calendar + Gmail** | the agents' actual hands | 3 |
| Observability | **Arize** | dashboard of every classification decision | 1 |
| Reliability | **Sentry** | error monitoring across the stack | 1 |

## Repo layout

```
thought-galaxy/
├── backend/          FastAPI — orchestrates Deepgram, Claude, Redis, agents
│   ├── app/
│   │   ├── main.py             entry + WebSocket for live transcription
│   │   ├── deepgram_stream.py  voice → text
│   │   ├── classify.py         Claude: transcript → bubble JSON
│   │   ├── suggest.py          Claude + Redis: bubble → suggestion  (M2)
│   │   ├── memory.py           Redis vector store + search          (M2)
│   │   ├── observability.py    Arize + Sentry setup
│   │   └── schemas.py          shared data shapes
│   └── requirements.txt
├── agents/           Fetch.ai uAgents
│   ├── insight_agent.py        suggestions from past context        (M2)
│   ├── calendar_agent.py       Google Calendar                      (M3)
│   ├── email_agent.py          Gmail                                (M3)
│   └── requirements.txt
├── frontend/         React + D3 bubble canvas
│   └── src/
│       ├── App.jsx
│       ├── Galaxy.jsx          the D3 force-directed map
│       ├── useRecorder.js      mic capture → backend WebSocket
│       └── api.js
└── .env.example      every key you need, in one place
```

## Quick start

```bash
# 1. Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # fill in your keys
uvicorn app.main:app --reload

# 2. Agents (separate terminal, Milestone 2+)
cd agents
pip install -r requirements.txt
python insight_agent.py

# 3. Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

## Division of labor (3 people)

- **Person A — Pipeline:** `deepgram_stream.py`, `classify.py`, the WebSocket in `main.py`. Owns voice→nodes.
- **Person B — Canvas:** all of `frontend/`. Owns the visual wow.
- **Person C — Agents + infra:** `agents/`, `memory.py`, `observability.py`. Owns Redis, Fetch.ai, Arize, Sentry.

A and B merge at Milestone 1. Then everyone converges on Milestone 2 before touching Milestone 3.
