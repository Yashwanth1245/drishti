import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { go } from "../App.jsx";

export default function SearchBar() {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const timer = useRef();

  useEffect(() => {
    clearTimeout(timer.current);
    if (q.trim().length < 2) { setRes(null); return; }
    timer.current = setTimeout(() => {
      api(`/api/search?q=${encodeURIComponent(q.trim())}`)
        .then(setRes).catch(console.error);
    }, 250);
    return () => clearTimeout(timer.current);
  }, [q]);

  const pick = (hash) => { setQ(""); setRes(null); go(hash); };

  return (
    <div className="searchbox">
      <input placeholder="Search person or FIR number…" value={q}
             onChange={(e) => setQ(e.target.value)} />
      {res && (res.entities.length || res.cases.length) > 0 && (
        <div className="results">
          {res.entities.map((e) => (
            <div key={e.entity_id} className="item"
                 onClick={() => pick(`/entity/${e.entity_id}`)}>
              <b>{e.canonical_name}</b>
              <span className="muted"> · {e.n_cases} case{e.n_cases > 1 ? "s" : ""}
                · {e.home_district} · risk {e.risk_score ?? "—"}</span>
            </div>
          ))}
          {res.cases.map((c) => (
            <div key={c.crime_no} className="item"
                 onClick={() => pick(`/case/${c.crime_no}`)}>
              <span className="mono">{c.crime_no}</span>
              <span className="muted"> · registered {c.registered}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
