import React, { useEffect, useState } from "react";
import { api, fmt, riskClass } from "../api.js";
import { go } from "../App.jsx";
import { useT } from "../i18n.js";

export default function EntityView({ entityId }) {
  const t = useT();
  const [e, setE] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    setE(null);
    setErr(null);            // clear a prior error, else a failed fetch wedges the view
    api(`/api/entities/${entityId}`).then(setE).catch((x) => setErr(String(x)));
  }, [entityId]);

  if (err) return <div className="err">{err}</div>;
  if (!e) return <div className="loading">Loading profile…</div>;

  const factors = Object.entries(e.risk_factors)
    .filter(([k]) => k !== "inputs");
  const age = e.birth_year_est ? 2026 - e.birth_year_est : null;

  return (
    <div className="pad">
      <a className="backlink" onClick={() => history.back()}>{t("ent.back")}</a>
      <div style={{ display: "flex", gap: 16, alignItems: "center",
                    marginBottom: 14 }}>
        <div>
          <h2 className="pagetitle" style={{ margin: 0 }}>{e.canonical_name}</h2>
          <div className="muted">
            {e.gender === "M" ? "Male" : "Female"}{age && <> · ~{age} yrs</>}
            · {e.n_cases} case{e.n_cases > 1 ? "s" : ""} · entity #{e.entity_id}
            · first seen {e.first_seen} · last seen {e.last_seen}
          </div>
        </div>
        <div style={{ marginLeft: "auto", textAlign: "center" }}>
          <div className={`badge-risk ${riskClass(e.risk_score)}`}>
            {e.risk_score ?? "—"}
          </div>
          <div className="muted" style={{ fontSize: 11 }}>{t("ent.risk")}</div>
        </div>
        <button className="chip accent" style={{ cursor: "pointer", fontSize: 13 }}
                onClick={() => go(`/network/${e.entity_id}`)}>
          {t("ent.viewnet")}
        </button>
      </div>

      <div className="grid31">
        <div>
          <div className="card">
            <h3>{t("ent.casehistory")} ({e.cases.length})</h3>
            {e.cases_outside_scope > 0 && (
              <div className="scopenote">
                {e.cases_outside_scope} case{e.cases_outside_scope > 1 && "s"} (marked 🔒)
                belong to other jurisdictions — case numbers and legal
                metadata are visible; victim/party details need an access
                request to the owning district.
              </div>
            )}
            <div className="timeline">
              {e.cases.map((c) => (
                <div key={c.crime_no} className="ev"
                     style={c.restricted ? { opacity: 0.75 } : null}>
                  <div>
                    <a className="mono" onClick={() => go(`/case/${c.crime_no}`)}>
                      {c.crime_no}
                    </a>
                    <span className="chip" style={{ marginLeft: 8 }}>{c.subhead}</span>
                    <span className={`chip ${c.status === "Under Investigation"
                      ? "warn" : c.status.includes("False") ? "danger" : "ok"}`}>
                      {c.status}
                    </span>
                    {c.restricted && <span className="chip">🔒 restricted</span>}
                  </div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {c.registered} · {c.station}, {c.district} · named as
                    “{c.shown_name}” · <i>{c.match_basis}</i>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div>
          <div className="card">
            <h3>{t("ent.whyrisk")}</h3>
            {factors.map(([k, f]) => (
              <div key={k} className="factor">
                <div className="lbl"><span>{k}</span>
                  <span>{Math.round(f.score * f.weight)} / {f.weight}</span></div>
                <div className="bar"><div style={{ width: `${f.score * 100}%` }} /></div>
              </div>
            ))}
            <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
              Composite of documented factors — decision support, not judgment.
            </div>
          </div>

          <div className="card">
            <h3>{t("ent.aliases")}</h3>
            {e.aliases.map((a) => <span key={a} className="chip">{a}</span>)}
          </div>

          {e.captured_ids.length > 0 && (
            <div className="card">
              <h3>{t("ent.captured")}</h3>
              <table className="t">
                <tbody>
                  {e.captured_ids.map((i, k) => (
                    <tr key={k}>
                      <td>{i.id_type}</td>
                      <td className="mono">{i.id_value}</td>
                      <td className="muted">{i.captured_on}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                Same identifier across records = certain identity link.
              </div>
            </div>
          )}

          {e.associates.length > 0 && (
            <div className="card">
              <h3>{t("ent.knownassoc")}</h3>
              {e.associates.map((a) => (
                <div key={a.entity_id} style={{ marginBottom: 6 }}>
                  <a onClick={() => go(`/entity/${a.entity_id}`)}>
                    {a.canonical_name}
                  </a>
                  <span className="muted"> · {a.edge_type} ×{a.weight}
                    · risk {a.risk_score ?? "—"}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
