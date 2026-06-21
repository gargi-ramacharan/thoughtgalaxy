const BASE = "http://localhost:8000";

export async function classifyText(transcript) {
  const r = await fetch(`${BASE}/classify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript }),
  });
  return r.json();
}

// Milestone 2 — ask a bubble for guidance
export async function suggest(nodeId, sessionId) {
  const r = await fetch(`${BASE}/suggest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_id: nodeId, session_id: sessionId }),
  });
  return r.json();
}

// Milestone 2 — search past thoughts
export async function searchPast(q) {
  const r = await fetch(`${BASE}/search?q=${encodeURIComponent(q)}`);
  return r.json();
}

// Milestone 3 — execute a task bubble
export async function execute(nodeId, sessionId) {
  const r = await fetch(`${BASE}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_id: nodeId, session_id: sessionId }),
  });
  return r.json();
}
