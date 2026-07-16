import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { go } from "../App.jsx";

// Ask-the-Data: the agentic lens. Every assistant answer carries evidence
// FIR chips and a collapsible tool trace ("how I got this") — the judged
// explainability requirement, visible in the UI itself.
const SUGGESTIONS = [
  "How many chain snatching cases in Dharwad in 2026?",
  "Tell me about Ravikumar B from Dharwad — history, aliases, associates",
  "Top risk offenders in Bengaluru Urban",
  "What alerts are active in Dharwad right now?",
];

export default function ChatView() {
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);

  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [msgs]);

  async function send(text) {
    const q = (text ?? input).trim();
    if (!q || busy) return;
    setInput("");
    const history = [...msgs, { role: "user", content: q }];
    setMsgs(history);
    setBusy(true);
    try {
      const d = await api("/api/chat", {
        method: "POST",
        json: {
          messages: history.map(({ role, content }) => ({ role, content })),
        },
      });
      setMsgs((m) => [...m, {
        role: "assistant",
        content: d.reply || d.detail || "(no reply)",
        evidence: d.evidence || [], trace: d.trace || [],
      }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", content: `Error: ${e}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pad" style={{ maxWidth: 900, margin: "0 auto" }}>
      <h2 className="pagetitle">Ask the data
        <span className="muted" style={{ fontSize: 13, marginLeft: 10 }}>
          GLM 4.7 on Zoho Catalyst · typed query tools only · every claim cited
        </span>
      </h2>

      {msgs.length === 0 && (
        <div className="card">
          <h3>Try asking</h3>
          {SUGGESTIONS.map((s) => (
            <div key={s} style={{ marginBottom: 6 }}>
              <a onClick={() => send(s)}>{s}</a>
            </div>
          ))}
        </div>
      )}

      {msgs.map((m, i) => (
        <div key={i} className="card" style={m.role === "user"
          ? { background: "var(--panel-2)", marginLeft: 60 }
          : { marginRight: 60 }}>
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
            {m.role === "user" ? "You" : "DRISHTI agent"}
          </div>
          <div style={{ whiteSpace: "pre-wrap" }}>{renderCited(m.content)}</div>
          {m.evidence?.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <span className="muted" style={{ fontSize: 11 }}>Evidence: </span>
              {m.evidence.slice(0, 12).map((cn) => (
                <span key={cn} className="chip mono accent rowlink"
                      onClick={() => go(`/case/${cn}`)}>{cn}</span>
              ))}
            </div>
          )}
          {m.trace?.length > 0 && (
            <details style={{ marginTop: 8 }}>
              <summary className="muted" style={{ fontSize: 12, cursor: "pointer" }}>
                How I got this ({m.trace.length} tool call{m.trace.length > 1 ? "s" : ""})
              </summary>
              {m.trace.map((t, k) => (
                <div key={k} className="mono"
                     style={{ fontSize: 11, margin: "6px 0", color: "var(--muted)" }}>
                  → {t.tool}({JSON.stringify(t.arguments)})
                  <div style={{ opacity: 0.7 }}>{t.result_preview?.slice(0, 200)}…</div>
                </div>
              ))}
            </details>
          )}
        </div>
      ))}
      {busy && <div className="loading">Agent is querying the database…</div>}
      <div ref={endRef} />

      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <input style={{ flex: 1, background: "var(--panel)", color: "var(--text)",
                        border: "1px solid var(--border)", borderRadius: 8,
                        padding: "10px 12px", fontSize: 14 }}
               placeholder="Ask about cases, offenders, alerts…" value={input}
               disabled={busy}
               onChange={(e) => setInput(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && send()} />
        <button className="chip accent" style={{ fontSize: 14, cursor: "pointer" }}
                disabled={busy} onClick={() => send()}>Send</button>
      </div>
    </div>
  );
}

// Make [CrimeNo] citations in the reply clickable.
function renderCited(text) {
  const parts = String(text).split(/\[(\d{15,20})\]/g);
  return parts.map((p, i) =>
    i % 2 === 1
      ? <a key={i} className="mono" onClick={() => go(`/case/${p}`)}>[{p}]</a>
      : p);
}
