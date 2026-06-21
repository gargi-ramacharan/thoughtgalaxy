# Build Plan — Thought Galaxy

A realistic schedule, the demo script, and the submission checklist. Tuned for
~14-16 productive hours with three people.

---

## Before the clock starts (Saturday morning / pre-event)

These don't count as "building during the event" — they're setup, and doing
them early saves you 3-4 hours of integration pain later.

- [ ] All three get accounts + API keys: Deepgram, Anthropic, Redis Cloud, Arize, Sentry
- [ ] Fetch.ai accounts ready (you have these)
- [ ] Google Cloud project: enable Calendar API + Gmail API, OAuth desktop creds → `google_credentials.json` (M3 only — can defer)
- [ ] Go to the **Deepgram workshop** and the **Fetch.ai workshop** first thing. Grab their starter code and credits.
- [ ] One person skims the uAgents quickstart so Fetch.ai isn't cold

---

## Hour-by-hour

### Hours 0-3 · Foundation (everyone)
- Clone scaffold, get `npm install` and `pip install` clean on all three machines
- **Person A:** get Deepgram streaming working in isolation — speak, see text in terminal
- **Person B:** get the Galaxy rendering with hardcoded fake nodes, tune the physics until it *feels* good
- **Person C:** Redis Cloud connected, Sentry + Arize keys in, `ensure_index()` runs

> Checkpoint: three pieces work alone. This is the riskiest integration moment — don't move on until Deepgram → terminal and fake-nodes → galaxy both work.

### Hours 3-7 · Milestone 1 (everyone converges)
- **A + B:** wire the WebSocket. Speak → partial transcript on screen → on pause, real bubbles bloom
- **C:** tune the Claude classification prompt with real rambles (record yourselves complaining about the hackathon — perfect test data)
- Make sure connections render and the type colors read clearly

> **Checkpoint: MILESTONE 1 DONE.** You now have a demoable, winning-on-its-own project. Lock it. Commit. Create the Devpost draft NOW (deadline midnight Saturday to guarantee judging).

### Hours 7-11 · Milestone 2
- **A:** build the suggestion flow end-to-end (`/suggest`)
- **C:** make Redis vector search real — replace the placeholder `_embed()` with a real embedding API (Voyage/OpenAI). This is what makes "you've felt this before" actually work
- **B:** the guidance card UI — slide-in, the "drew on" past-context line
- Optional but high-value: stand up the **Insight Agent** as a real Fetch.ai uAgent so the suggestion goes through Agentverse, not just a function call. That's what earns the Fetch.ai prize.

> Checkpoint: tap a stress bubble → grounded suggestion referencing a real past session. Commit.

### Hours 11-14 · Milestone 3 (only if M2 is solid)
- **C:** Calendar Agent live — task bubble → real Google Calendar event
- **A:** Email Agent → Gmail *draft* (never auto-send on stage)
- **B:** execute button + status states on the card
- Wire the agent bridge; ideally route through Fetch.ai messaging for the multi-agent story (Band prize: 2+ agents collaborating)

> Checkpoint: click execute → event appears in calendar. This is the closer.

### Hours 14-16 · Polish + demo prep (everyone)
- Record a **backup demo video** in case wifi dies — this is non-negotiable
- Pre-load a session with good past data so M2 suggestions land well
- Write and rehearse the 4-min pitch (below)
- Final Devpost: writeup, screenshots, repo link, video
- **Simular:** post on X/LinkedIn tagging them + email zening@simular.ai if you used Sai at all (even just to vibe-code part of it)

---

## The 4-minute pitch

1. **(0:00-0:30) The feeling.** "Come home overwhelmed, brain full of half-thoughts — I have a midterm, I'm behind on homework, I think my friend's mad at me. No app helps with that, because your brain doesn't think in checklists." Don't show the screen yet.
2. **(0:30-2:00) Live demo, M1.** Talk through a real messy day. Let the bubbles bloom live. Let them watch the connections draw. This is the whole game — let it breathe.
3. **(2:00-2:45) Guidance, M2.** Tap the stress bubble. Ask what to do. Show the suggestion pulling from a past session. "It knows I've been here before."
4. **(2:45-3:20) Action, M3.** Click execute on a task bubble. Cut to the calendar — it's there. "From a thought I spoke, to a thing that's done."
5. **(3:20-4:00) Stack + vision.** Quick: Deepgram voice, Claude reasoning, Fetch.ai agents, Redis memory. "This is a map of your whole inner life — and it acts on itself." End on the galaxy, full of bubbles.

**If a piece breaks live:** the `/classify` REST endpoint is your fallback — type the transcript instead of speaking. The backup video is your hard floor.

---

## Sponsor checklist (what to actually claim)

| Sponsor | Eligible because | Do this to qualify |
|---|---|---|
| Deepgram | streaming STT is the input | works out of the box |
| Anthropic | Claude is the reasoning core + built with Claude Code | mention Claude Code in writeup |
| Fetch.ai | Insight/Calendar/Email as uAgents | register at least one on Agentverse |
| Redis | vector search + agent memory | real embeddings, show the search |
| Arize | classification logged + dashboard | screenshot the dashboard for judges |
| Sentry | error monitoring across stack | just keep the DSN set |
| Band | 2+ agents collaborating (M3) | route a task through 2 agents |
| Simular | if you vibe-code with Sai | post + email per their rules |

Realistic target if you ship M1+M2: Deepgram, Anthropic, Fetch.ai, Redis, Arize, Sentry. Add Band + Simular if M3 lands.

---

## Track choice

Primary: **Ddoski's World** (mental clarity / wellbeing access) OR **Ddoski's Toolbox** (a genuinely useful personal tool). World has the stronger story for VC judges; Toolbox rewards usefulness. Pick World unless the build leans hard utility.

Also auto-considered: **Best UI/UX** (the galaxy is your best shot — make it beautiful), **Golden Bear** (frame the demo around a Berkeley student's day), **Hacker's Choice** (the live demo wins hearts).
