// Minimal, dependency-free i18n for the DRISHTI interface (English / Kannada).
//
// A module-level current language + a useSyncExternalStore subscription so any
// component that calls useT() re-renders the instant the language flips — no
// context provider to thread, no remount (the MapLibre map survives a switch).
// DATA stays as-is (names, districts, numbers, FIR content); only the interface
// chrome and section labels translate.
import { useSyncExternalStore } from "react";

const KEY = "drishti_lang";
let lang = localStorage.getItem(KEY) || "en";
const listeners = new Set();

export function getLang() { return lang; }
export function setLang(l) {
  lang = l === "kn" ? "kn" : "en";
  localStorage.setItem(KEY, lang);
  listeners.forEach((fn) => fn());
}
function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }

// t(key[, fallback]) — current-language string; falls back to English then the
// key itself, so a missing translation degrades gracefully instead of blanking.
export function t(key, fallback) {
  const d = DICT[lang] || DICT.en;
  return d[key] ?? DICT.en[key] ?? fallback ?? key;
}
// Hook: subscribes to language changes and returns the (stable) t function.
export function useT() {
  useSyncExternalStore(subscribe, getLang, getLang);
  return t;
}
export function useLang() {
  return useSyncExternalStore(subscribe, getLang, getLang);
}

const DICT = {
  en: {
    "app.tagline": "KARNATAKA CRIME INTELLIGENCE — SYNTHETIC DATA PROTOTYPE",
    "app.signout": "Sign out",
    "app.loading": "Loading DRISHTI…",
    "search.ph": "Search person or FIR number…",
    "tab.map": "Command map", "tab.trends": "Trends", "tab.alerts": "Alerts",
    "tab.network": "Network", "tab.chat": "Ask the data", "tab.scan": "Scan FIR",
    "tab.audit": "Audit",
    "kpi.firs30": "FIRs, last 30 days", "kpi.open": "Open investigations",
    "kpi.csrate": "Chargesheet rate", "kpi.median": "Median days to chargesheet",
    "kpi.property": "Property value recovered",
    "kpi.repeat": "Repeat offenders (resolved)", "kpi.alerts": "Active alerts",
    "login.username": "Username", "login.password": "Password",
    "login.signin": "Sign in", "login.signingin": "Signing in…",
    "login.demo": "DEMO ROLES — one click each · access is enforced server-side by rank",
    "map.title": "COMMAND MAP", "map.hide": "hide ⟨", "map.allheads": "All crime heads",
    "map.allhours": "All hours",
    "map.hint": "Circle size = case volume · pulsing red = the hottest spike zones. Click a district to drill in.",
    "map.leaderboard": "HIGHEST RATE PER LAKH", "map.controls": "Map controls",
    "trends.title": "Crime trends", "trends.allka": "All Karnataka",
    "trends.spikes": "Active spikes in scope",
    "alerts.title": "Early-warning alerts", "alerts.brief": "Generate brief",
    "ent.knownassoc": "Known associates",
    "net.title": "Criminal networks",
    "net.subtitle": "most-connected offenders statewide · resolved by entity resolution · pick one to open their association graph",
    "net.assoc": "known associates", "net.graphtitle": "CRIMINAL NETWORK",
    "ent.casehistory": "CASE HISTORY", "ent.whyrisk": "WHY THIS RISK SCORE",
    "ent.aliases": "KNOWN NAMES / SPELLINGS", "ent.captured": "CAPTURED IDENTIFIERS",
    "ent.risk": "risk score", "ent.viewnet": "View network →", "ent.back": "← back",
    "ent.cases": "cases",
    "case.brief": "Brief facts", "case.timeline": "Timeline",
    "case.similar": "Similar past cases (shared MO)", "case.sections": "Sections",
    "case.parties": "Parties", "case.complainant": "Complainant",
    "case.victims": "Victims", "case.accused": "Accused", "case.mo": "Modus operandi",
    "case.property": "Property", "case.capturedids": "Captured identifiers",
    "case.unknown": "Unknown", "case.reqaccess": "Request access →",
    "case.restricted": "Restricted record.",
    "chat.title": "Ask the data",
    "chat.subtitle": "GLM 4.7 on Zoho Catalyst · typed query tools only · every claim cited",
    "chat.try": "Try asking", "chat.you": "You", "chat.agent": "DRISHTI agent",
    "chat.evidence": "Evidence: ", "chat.howigot": "How I got this",
    "chat.ph": "Ask about cases, offenders, alerts…", "chat.send": "Send",
    "chat.querying": "Agent is querying the database…",
    "scan.title": "Scan a paper FIR", "audit.title": "Audit trail",
  },
  kn: {
    // topbar / chrome
    "app.tagline": "ಕರ್ನಾಟಕ ಅಪರಾಧ ಗುಪ್ತಚರ — ಕೃತಕ ದತ್ತಾಂಶ ಮಾದರಿ",
    "app.signout": "ಸೈನ್ ಔಟ್",
    "app.loading": "DRISHTI ಲೋಡ್ ಆಗುತ್ತಿದೆ…",
    "search.ph": "ವ್ಯಕ್ತಿ ಅಥವಾ FIR ಸಂಖ್ಯೆ ಹುಡುಕಿ…",
    // tabs
    "tab.map": "ಕಮಾಂಡ್ ನಕ್ಷೆ",
    "tab.trends": "ಪ್ರವೃತ್ತಿಗಳು",
    "tab.alerts": "ಎಚ್ಚರಿಕೆಗಳು",
    "tab.network": "ಜಾಲ",
    "tab.chat": "ದತ್ತಾಂಶ ಕೇಳಿ",
    "tab.scan": "FIR ಸ್ಕ್ಯಾನ್",
    "tab.audit": "ಲೆಕ್ಕಪರಿಶೋಧನೆ",
    // KPI strip
    "kpi.firs30": "FIRಗಳು, ಕಳೆದ 30 ದಿನ",
    "kpi.open": "ತೆರೆದ ತನಿಖೆಗಳು",
    "kpi.csrate": "ಆರೋಪಪಟ್ಟಿ ದರ",
    "kpi.median": "ಆರೋಪಪಟ್ಟಿಗೆ ಸರಾಸರಿ ದಿನಗಳು",
    "kpi.property": "ಮರಳಿ ಪಡೆದ ಆಸ್ತಿ ಮೌಲ್ಯ",
    "kpi.repeat": "ಪುನರಾವರ್ತಿತ ಅಪರಾಧಿಗಳು",
    "kpi.alerts": "ಸಕ್ರಿಯ ಎಚ್ಚರಿಕೆಗಳು",
    // login
    "login.username": "ಬಳಕೆದಾರ ಹೆಸರು",
    "login.password": "ಪಾಸ್‌ವರ್ಡ್",
    "login.signin": "ಸೈನ್ ಇನ್",
    "login.signingin": "ಸೈನ್ ಇನ್ ಆಗುತ್ತಿದೆ…",
    "login.demo": "ಡೆಮೊ ಪಾತ್ರಗಳು — ಒಂದೊಂದು ಕ್ಲಿಕ್ · ಪ್ರವೇಶವು ಶ್ರೇಣಿ ಆಧಾರಿತವಾಗಿ ಸರ್ವರ್‌ನಲ್ಲಿ ಜಾರಿಯಾಗುತ್ತದೆ",
    // map
    "map.title": "ಕಮಾಂಡ್ ನಕ್ಷೆ",
    "map.hide": "ಮರೆಮಾಡಿ",
    "map.allheads": "ಎಲ್ಲಾ ಅಪರಾಧ ವಿಭಾಗಗಳು",
    "map.allhours": "ಎಲ್ಲಾ ಸಮಯ",
    "map.hint": "ವೃತ್ತದ ಗಾತ್ರ = ಪ್ರಕರಣ ಪ್ರಮಾಣ · ಮಿನುಗುವ ಕೆಂಪು = ಅತಿ ಹೆಚ್ಚು ಸ್ಪೈಕ್ ವಲಯಗಳು. ವಿವರಕ್ಕೆ ಜಿಲ್ಲೆ ಕ್ಲಿಕ್ ಮಾಡಿ.",
    "map.leaderboard": "ಪ್ರತಿ ಲಕ್ಷಕ್ಕೆ ಅತ್ಯಧಿಕ ದರ",
    "map.controls": "ನಕ್ಷೆ ನಿಯಂತ್ರಣಗಳು",
    // trends
    "trends.title": "ಅಪರಾಧ ಪ್ರವೃತ್ತಿಗಳು",
    "trends.allka": "ಇಡೀ ಕರ್ನಾಟಕ",
    "trends.spikes": "ವ್ಯಾಪ್ತಿಯಲ್ಲಿನ ಸಕ್ರಿಯ ಸ್ಪೈಕ್‌ಗಳು",
    // alerts
    "alerts.title": "ಮುನ್ನೆಚ್ಚರಿಕೆ ಎಚ್ಚರಿಕೆಗಳು",
    "alerts.brief": "ಸಂಕ್ಷಿಪ್ತ ವರದಿ ರಚಿಸಿ",
    "ent.knownassoc": "ತಿಳಿದ ಸಹಚರರು",
    // network
    "net.title": "ಅಪರಾಧ ಜಾಲಗಳು",
    "net.subtitle": "ರಾಜ್ಯದ ಅತಿ ಹೆಚ್ಚು ಸಂಪರ್ಕಿತ ಅಪರಾಧಿಗಳು · ಗುರುತು ಪರಿಹಾರದಿಂದ · ಒಂದನ್ನು ಆರಿಸಿ",
    "net.assoc": "ತಿಳಿದ ಸಹಚರರು",
    "net.graphtitle": "ಅಪರಾಧ ಜಾಲ",
    // entity profile
    "ent.casehistory": "ಪ್ರಕರಣ ಇತಿಹಾಸ",
    "ent.whyrisk": "ಈ ಅಪಾಯ ಸ್ಕೋರ್ ಏಕೆ",
    "ent.aliases": "ತಿಳಿದ ಹೆಸರುಗಳು / ಕಾಗುಣಿತಗಳು",
    "ent.captured": "ಸೆರೆಹಿಡಿದ ಗುರುತುಗಳು",
    "ent.risk": "ಅಪಾಯ ಸ್ಕೋರ್",
    "ent.viewnet": "ಜಾಲ ನೋಡಿ",
    "ent.back": "← ಹಿಂದೆ",
    "ent.cases": "ಪ್ರಕರಣಗಳು",
    // case detail
    "case.brief": "ಸಂಕ್ಷಿಪ್ತ ವಿವರ",
    "case.timeline": "ಕಾಲಾನುಕ್ರಮ",
    "case.similar": "ಸಮಾನ ಹಿಂದಿನ ಪ್ರಕರಣಗಳು (ಹಂಚಿದ MO)",
    "case.sections": "ಕಲಂಗಳು",
    "case.parties": "ಪಕ್ಷಗಳು",
    "case.complainant": "ದೂರುದಾರ",
    "case.victims": "ಸಂತ್ರಸ್ತರು",
    "case.accused": "ಆರೋಪಿ",
    "case.mo": "ಅಪರಾಧ ವಿಧಾನ (MO)",
    "case.property": "ಆಸ್ತಿ",
    "case.capturedids": "ಸೆರೆಹಿಡಿದ ಗುರುತುಗಳು",
    "case.unknown": "ಅಜ್ಞಾತ",
    "case.reqaccess": "ಪ್ರವೇಶ ವಿನಂತಿಸಿ →",
    "case.restricted": "ನಿರ್ಬಂಧಿತ ದಾಖಲೆ.",
    // chat
    "chat.title": "ದತ್ತಾಂಶ ಕೇಳಿ",
    "chat.subtitle": "Zoho Catalyst ನಲ್ಲಿ GLM 4.7 · ಟೈಪ್ ಮಾಡಿದ ಪ್ರಶ್ನೆ ಉಪಕರಣಗಳು ಮಾತ್ರ · ಪ್ರತಿ ಹೇಳಿಕೆಗೂ ಆಧಾರ",
    "chat.try": "ಕೇಳಿ ನೋಡಿ",
    "chat.you": "ನೀವು",
    "chat.agent": "DRISHTI ಏಜೆಂಟ್",
    "chat.evidence": "ಆಧಾರ: ",
    "chat.howigot": "ನಾನು ಇದನ್ನು ಹೇಗೆ ಪಡೆದೆ",
    "chat.ph": "ಪ್ರಕರಣ, ಅಪರಾಧಿ, ಎಚ್ಚರಿಕೆ ಬಗ್ಗೆ ಕೇಳಿ…",
    "chat.send": "ಕಳುಹಿಸಿ",
    "chat.querying": "ಏಜೆಂಟ್ ದತ್ತಾಂಶ ಪರಿಶೀಲಿಸುತ್ತಿದೆ…",
    // scan
    "scan.title": "ಕಾಗದದ FIR ಸ್ಕ್ಯಾನ್ ಮಾಡಿ",
    // audit
    "audit.title": "ಲೆಕ್ಕಪರಿಶೋಧನಾ ಜಾಡು",
  },
};
