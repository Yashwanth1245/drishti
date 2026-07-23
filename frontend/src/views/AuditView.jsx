import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { useT } from "../i18n.js";

// The audit trail lens (state roles only): the accountability record — who
// searched which name, who opened whose profile / which FIR, what was asked
// of the AI, sign-ins, and every DENIED attempt (highlighted, because
// denials prove enforcement). Dashboard navigation is deliberately not
// logged; this is an audit trail, not a request log.
const EVENT_CHIP = {
  "access-denied": "danger",
  "login-failed": "danger",
  "access-request": "warn",
  "login": "ok",
  "chat": "accent",
  "brief": "accent",
  "scan-ingest": "accent",
};

export default function AuditView() {
  const t = useT();
  const [entries, setEntries] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api("/api/audit?limit=120")
        .then((r) => alive && setEntries(r.entries))
        .catch((x) => alive && setErr(x.message));
    load();
    const t = setInterval(load, 5000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (err) return <div className="err">{err}</div>;
  if (!entries) return <div className="loading">Loading audit trail…</div>;

  return (
    <div className="pad">
      <h2 className="pagetitle">{t("audit.title")}
        <span className="muted" style={{ fontSize: 13, marginLeft: 10 }}>
          record access · AI usage · sign-ins · denials — x_audit_log
        </span>
      </h2>
      <div className="card" style={{ overflowX: "auto" }}>
        <table className="t audit-t">
          <thead>
            <tr><th>time (UTC)</th><th>user</th><th>role</th><th>event</th>
                <th>what happened</th></tr>
          </thead>
          <tbody>
            {entries.map((e, i) => (
              <tr key={e.log_id ?? i}
                  className={e.event === "access-denied" ? "audit-denied" : ""}>
                <td className="mono">{e.ts}</td>
                <td>{e.user}</td>
                <td className="muted">{e.role || "—"}</td>
                <td><span className={`chip ${EVENT_CHIP[e.event] || ""}`}>
                  {e.event}</span></td>
                <td style={{ maxWidth: 520 }}>{e.summary}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {entries.length === 0 && (
          <div className="muted" style={{ padding: 10 }}>
            No audited actions yet — open a profile, run a search, or ask the
            data.
          </div>
        )}
      </div>
    </div>
  );
}
