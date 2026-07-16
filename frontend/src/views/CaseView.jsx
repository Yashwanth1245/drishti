import React, { useEffect, useState } from "react";
import { api, fmt } from "../api.js";
import { go } from "../App.jsx";

export default function CaseView({ crimeNo }) {
  const [c, setC] = useState(null);
  const [err, setErr] = useState(null);
  const [reqState, setReqState] = useState(null);   // null | "busy" | message

  useEffect(() => {
    setC(null);
    setReqState(null);
    api(`/api/cases/${crimeNo}`).then(setC).catch((x) => setErr(String(x)));
  }, [crimeNo]);

  async function requestAccess() {
    setReqState("busy");
    try {
      const r = await api(`/api/cases/${crimeNo}/request-access`,
                          { method: "POST" });
      setReqState(r.message);
    } catch (x) {
      setReqState(String(x));
    }
  }

  if (err) return <div className="err">{err}</div>;
  if (!c) return <div className="loading">Loading case…</div>;
  const restricted = c.access === "restricted";

  return (
    <div className="pad">
      <a className="backlink" onClick={() => history.back()}>← back</a>
      <h2 className="pagetitle">
        FIR <span className="mono">{c.CrimeNo}</span>
        <span className="chip" style={{ marginLeft: 10 }}>{c.head}</span>
        <span className="chip accent">{c.subhead}</span>
        <span className={`chip ${c.gravity === "Heinous" ? "danger" : ""}`}>
          {c.gravity}
        </span>
        <span className={`chip ${c.status === "Under Investigation" ? "warn" : "ok"}`}>
          {c.status}
        </span>
      </h2>

      {restricted && (
        <div className="scopenote" style={{ marginBottom: 12 }}>
          <b>Restricted record.</b> {c.restriction_note}{" "}
          {reqState === null && (
            <a onClick={requestAccess} style={{ fontWeight: 600 }}>
              Request access →
            </a>
          )}
          {reqState === "busy" && <i>recording request…</i>}
          {reqState && reqState !== "busy" && <i>{reqState}</i>}
        </div>
      )}

      <div className="grid31">
        <div>
          <div className="card">
            <h3>Brief facts</h3>
            {restricted
              ? <div className="muted">Narrative restricted to the owning
                  jurisdiction.</div>
              : <div className="brief">{c.BriefFacts}</div>}
          </div>

          <div className="card">
            <h3>Timeline</h3>
            <div className="timeline">
              <div className="ev">Incident: <b>{c.IncidentFromDate}</b>
                <span className="muted"> → {c.IncidentToDate}</span></div>
              <div className="ev">Reported to PS: <b>{c.InfoReceivedPSDate}</b></div>
              <div className="ev">FIR registered: <b>{c.CrimeRegisteredDate}</b>
                <span className="muted"> at {c.station}, {c.district}
                  {c.io_name && <> · IO {c.io_name}</>}</span></div>
              {c.arrests.map((a, i) => (
                <div key={i} className="ev">Arrest: <b>{a.date}</b></div>
              ))}
              {c.chargesheet.map((s, i) => (
                <div key={i} className="ev">
                  Final report ({s.cstype === "A" ? "chargesheet"
                    : s.cstype === "B" ? "false case" : "undetected"}):
                  <b> {s.date}</b>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <h3>Similar past cases (shared MO)</h3>
            {c.similar_cases.length === 0 && <div className="muted">None found.</div>}
            <table className="t">
              <tbody>
                {c.similar_cases.map((s) => (
                  <tr key={s.crime_no} className="rowlink"
                      onClick={() => go(`/case/${s.crime_no}`)}>
                    <td className="mono">{s.crime_no}</td>
                    <td>{s.district}</td>
                    <td>{s.registered}</td>
                    <td>{s.shared_tags} shared MO tag{s.shared_tags > 1 ? "s" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="card">
            <h3>Sections</h3>
            {c.sections.map((s, i) => (
              <span key={i} className="chip mono">{s.act} {s.section}</span>
            ))}
          </div>

          <div className="card">
            <h3>Parties</h3>
            <div className="muted" style={{ fontSize: 12 }}>Complainant</div>
            {restricted
              ? <div className="muted">🔒 {c.redacted?.complainants ?? 0} on
                  record — details restricted</div>
              : c.complainants.map((p, i) => <div key={i}>{p.name} ({p.age})</div>)}
            {restricted && c.redacted?.victims > 0 && (
              <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                Victims<br />
                <span>🔒 {c.redacted.victims} on record — details restricted</span>
              </div>
            )}
            {!restricted && c.victims.length > 0 && <>
              <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>Victims</div>
              {c.victims.map((p, i) => <div key={i}>{p.name} ({p.age}/{p.gender})</div>)}
            </>}
            <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>Accused</div>
            {c.accused.length === 0 && <div className="muted">Unknown</div>}
            {c.accused.map((p) => (
              <div key={p.AccusedMasterID}>
                {p.entity_id
                  ? <a onClick={() => go(`/entity/${p.entity_id}`)}>{p.name}</a>
                  : p.name}
                <span className="muted"> ({p.age}/{p.gender}) · {p.ordinal}</span>
              </div>
            ))}
          </div>

          {c.mo_tags.length > 0 && (
            <div className="card">
              <h3>Modus operandi</h3>
              {c.mo_tags.map((t) => <span key={t} className="chip warn">{t}</span>)}
            </div>
          )}

          {restricted && (c.redacted?.property > 0
                          || c.redacted?.captured_ids > 0) && (
            <div className="card">
              <h3>Restricted sections</h3>
              <div className="muted" style={{ fontSize: 13 }}>
                {c.redacted.property > 0 &&
                  <div>🔒 Property: {c.redacted.property} item(s)</div>}
                {c.redacted.captured_ids > 0 &&
                  <div>🔒 Captured identifiers: {c.redacted.captured_ids}</div>}
                Visible after the owning district approves access.
              </div>
            </div>
          )}

          {c.property.length > 0 && (
            <div className="card">
              <h3>Property</h3>
              {c.property.map((p, i) => (
                <div key={i} style={{ marginBottom: 6 }}>
                  {p.description}
                  <div className="muted" style={{ fontSize: 12 }}>
                    ₹{fmt(p.value_inr)} · {p.recovered ? "recovered" : "not recovered"}
                    {p.identifier && <> · <span className="mono">{p.identifier}</span></>}
                  </div>
                </div>
              ))}
            </div>
          )}

          {c.captured_ids.length > 0 && (
            <div className="card">
              <h3>Captured identifiers</h3>
              {c.captured_ids.map((i, k) => (
                <div key={k} style={{ fontSize: 13 }}>
                  <span className="muted">{i.role} · {i.id_type}: </span>
                  <span className="mono">{i.id_value}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
