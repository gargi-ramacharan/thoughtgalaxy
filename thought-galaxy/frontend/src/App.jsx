import { useState, useCallback } from "react";
import Galaxy from "./Galaxy";
import { useRecorder } from "./useRecorder";
import { suggest, execute } from "./api";
import "./styles.css";

/**
 * App — the full Thought Galaxy experience.
 *
 *  M1: hold to talk → live transcript → bubbles bloom into a galaxy
 *  M2: tap a bubble → a guidance card slides in, grounded in past sessions
 *  M3: a task bubble's card shows Execute → an agent runs it
 */
export default function App() {
  const [nodes, setNodes] = useState([]);
  const [partial, setPartial] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [card, setCard] = useState(null); // {node, suggestion?, loading?}

  const onNodes = useCallback((incoming) => {
    setNodes((prev) => {
      const byId = new Map(prev.map((n) => [n.id, n]));
      incoming.forEach((n) => byId.set(n.id, { ...byId.get(n.id), ...n }));
      return [...byId.values()];
    });
  }, []);

  const { recording, start, stop } = useRecorder({
    onPartial: setPartial,
    onNodes,
  });

  // M2 — tap a bubble for guidance
  const onTap = useCallback(
    async (node) => {
      setCard({ node, loading: true });
      try {
        const s = await suggest(node.id, sessionId);
        setCard({ node, suggestion: s.text, drawnFrom: s.drawn_from });
      } catch {
        setCard({ node, suggestion: "Couldn't reach the guidance agent." });
      }
    },
    [sessionId]
  );

  // M3 — run an agent on a task bubble
  const onExecute = useCallback(
    async (node) => {
      setCard((c) => ({ ...c, executing: true }));
      const res = await execute(node.id, sessionId);
      setCard((c) => ({ ...c, executing: false, result: res }));
    },
    [sessionId]
  );

  return (
    <div className="app">
      <header>
        <h1>Thought Galaxy</h1>
        <p className="tag">say what's on your mind — watch it organize itself</p>
      </header>

      <div className="canvas">
        <Galaxy nodes={nodes} onTap={onTap} />
        {nodes.length === 0 && !recording && (
          <div className="empty">Hold the orb and talk through your day.</div>
        )}
      </div>

      {partial && recording && <div className="partial">{partial}</div>}

      <button
        className={`orb ${recording ? "live" : ""}`}
        onMouseDown={start}
        onMouseUp={stop}
        onTouchStart={start}
        onTouchEnd={stop}
      >
        {recording ? "listening…" : "hold to talk"}
      </button>

      {card && (
        <div className="card" onClick={(e) => e.stopPropagation()}>
          <button className="close" onClick={() => setCard(null)}>×</button>
          <div className={`chip ${card.node.type}`}>{card.node.type}</div>
          <h3>{card.node.text}</h3>

          {card.loading && <p className="muted">thinking it through…</p>}

          {card.suggestion && <p className="suggestion">{card.suggestion}</p>}

          {card.drawnFrom?.length > 0 && (
            <p className="drawn">drew on: {card.drawnFrom.join(" · ")}</p>
          )}

          {/* M3 — only task bubbles can be executed */}
          {card.node.type === "task" && !card.result && (
            <button
              className="exec"
              disabled={card.executing}
              onClick={() => onExecute(card.node)}
            >
              {card.executing ? "running…" : "let an agent handle it"}
            </button>
          )}

          {card.result && (
            <p className={card.result.status === "done" ? "ok" : "fail"}>
              {card.result.status === "done"
                ? "done — check your calendar / drafts"
                : "couldn't complete that one"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
