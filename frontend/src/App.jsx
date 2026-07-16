import React, { useEffect, useMemo, useState } from "react";
import { api, clearSession, fmt, getUser, setSession } from "./api.js";
import AlertsView from "./views/AlertsView.jsx";
import AuditView from "./views/AuditView.jsx";
import CaseView from "./views/CaseView.jsx";
import ChatView from "./views/ChatView.jsx";
import EntityView from "./views/EntityView.jsx";
import LoginView from "./views/LoginView.jsx";
import MapView from "./views/MapView.jsx";
import NetworkView from "./views/NetworkView.jsx";
import ScanView from "./views/ScanView.jsx";
import SearchBar from "./views/SearchBar.jsx";
import TrendsView from "./views/TrendsView.jsx";

// Tiny hash router: #/map, #/trends, #/alerts, #/network/<id>,
// #/entity/<id>, #/case/<crimeNo> — deep-linkable for the demo.
function useRoute() {
  const [hash, setHash] = useState(window.location.hash || "#/map");
  useEffect(() => {
    const on = () => setHash(window.location.hash || "#/map");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const parts = hash.replace(/^#\//, "").split("/");
  return { view: parts[0] || "map", arg: parts.slice(1).join("/") || null };
}

export const go = (hash) => { window.location.hash = hash; };

const TABS = [
  ["map", "Command map"],
  ["trends", "Trends"],
  ["alerts", "Alerts"],
  ["network", "Network"],
  ["chat", "Ask the data"],
  ["scan", "Scan FIR"],
];

export default function App() {
  const { view, arg } = useRoute();
  const [user, setUser] = useState(getUser());
  const [kpis, setKpis] = useState(null);
  const [meta, setMeta] = useState(null);

  // api.js clears the session on any 401 and fires this event.
  useEffect(() => {
    const on = () => setUser(getUser());
    window.addEventListener("drishti-auth", on);
    return () => window.removeEventListener("drishti-auth", on);
  }, []);

  useEffect(() => {
    if (!user) return;
    setKpis(null);
    setMeta(null);
    api("/api/kpis").then(setKpis).catch(console.error);
    api("/api/meta").then(setMeta).catch(console.error);
  }, [user]);

  // The audit lens exists only for state-level roles; the server enforces
  // the same rule (403) — hiding the tab is UX, not security.
  const tabs = useMemo(() => (
    user?.scope_type === "state" ? [...TABS, ["audit", "Audit"]] : TABS
  ), [user]);

  const body = useMemo(() => {
    if (!user) return null;
    if (!meta) return <div className="loading">Loading DRISHTI…</div>;
    if (view === "map") return <MapView meta={meta} />;
    if (view === "trends") return <TrendsView meta={meta} />;
    if (view === "alerts") return <AlertsView />;
    if (view === "network") return <NetworkView entityId={arg} />;
    if (view === "chat") return <ChatView />;
    if (view === "scan") return <ScanView />;
    if (view === "audit") return <AuditView />;
    if (view === "entity") return <EntityView entityId={arg} />;
    if (view === "case") return <CaseView crimeNo={arg} />;
    return <div className="err">Unknown view: {view}</div>;
  }, [view, arg, meta, user]);

  if (!user) return <LoginView />;

  return (
    <div className="shell">
      <div className="topbar">
        <div className="brand">
          DRISHTI<span className="kn">ದೃಷ್ಟಿ</span>
          <small>KARNATAKA CRIME INTELLIGENCE — SYNTHETIC DATA PROTOTYPE</small>
        </div>
        <RoleSwitcher user={user} />
        <button className="logout" onClick={() => { clearSession(); go("/map"); }}>
          Sign out
        </button>
      </div>

      {kpis && (
        <div className="kpis">
          <Kpi v={fmt(kpis.cases_last_30d)} l="FIRs, last 30 days"
               delta={kpis.yoy_change_pct} onClick={() => go("/trends")} />
          <Kpi v={fmt(kpis.open_investigations)} l="Open investigations" />
          <Kpi v={`${kpis.chargesheet_rate_pct ?? "—"}%`} l="Chargesheet rate" />
          <Kpi v={fmt(kpis.median_days_to_chargesheet)} l="Median days to chargesheet" />
          <Kpi v={`${kpis.property_recovery_pct ?? "—"}%`}
               l="Property value recovered" />
          <Kpi v={fmt(kpis.repeat_offender_entities)}
               l="Repeat offenders (resolved)" onClick={() => go("/network")} />
          <Kpi v={fmt(kpis.active_alerts)} l="Active alerts" hot
               onClick={() => go("/alerts")} />
        </div>
      )}

      <div className="nav">
        {tabs.map(([id, label]) => (
          <button key={id} className={view === id ? "active" : ""}
                  onClick={() => go(`/${id}`)}>{label}</button>
        ))}
        <SearchBar />
      </div>

      <div className="main">{body}</div>
    </div>
  );
}

// Demo affordance: the role chip is a dropdown that re-logs-in as the picked
// rank in one click (no sign-out roundtrip for judges). It is UX sugar only —
// each switch is a REAL login (fresh token, server-side scoping, and the
// switch itself appears in the audit trail as a login event).
function RoleSwitcher({ user }) {
  const [demo, setDemo] = useState(null);

  useEffect(() => {
    api("/api/auth/demo").then(setDemo).catch(() => setDemo(null));
  }, []);

  async function switchTo(username) {
    if (!demo || username === user.username) return;
    try {
      const r = await api("/api/auth/login", {
        method: "POST", json: { username, password: demo.password },
      });
      // Leaving a state-only lens? Land somewhere every rank can see.
      if (window.location.hash.startsWith("#/audit")
          && r.user.scope_type !== "state") go("/map");
      setSession(r.token, r.user);
    } catch (e) {
      console.error("role switch failed", e);
    }
  }

  if (!demo?.accounts?.length) {
    return <div className="rolechip">{user.label}</div>;
  }
  return (
    <select className="rolechip roleswitch" value={user.username}
            title="Demo: switch rank — access is enforced server-side"
            onChange={(e) => switchTo(e.target.value)}>
      {demo.accounts.map((a) => (
        <option key={a.username} value={a.username}>{a.label}</option>
      ))}
    </select>
  );
}

function Kpi({ v, l, delta, hot, onClick }) {
  // Evidence doctrine, applied to the strip: a number with a lens behind it
  // is a door, not a label.
  return (
    <div className={`kpi${onClick ? " kpi-link" : ""}`} onClick={onClick}>
      <div className="v" style={hot ? { color: "var(--danger)" } : null}>
        {v}
        {delta != null && (
          <span className={delta >= 0 ? "delta-up" : "delta-down"}>
            {delta >= 0 ? "▲" : "▼"} {Math.abs(delta)}%
          </span>
        )}
      </div>
      <div className="l">{l}</div>
    </div>
  );
}
