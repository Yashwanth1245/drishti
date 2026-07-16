"""API check: correctness against the planted stories + latency targets +
the Phase-5 RBAC contract.

Runs the FastAPI app in-process (TestClient), walks the demo storyline through
the actual endpoints AS THE DGP, then walks the rank ladder (DIG range, SP
district, station IO) asserting that jurisdiction scoping and the audit trail
behave exactly as documented in ARCHITECTURE.md. Run from backend/:

    ../.venv/bin/python -m app.apicheck
"""

import json
import os
import sys
import time

os.environ.setdefault("DRISHTI_RATELIMIT", "0")   # don't rate-limit the test burst

from fastapi.testclient import TestClient

from .auth import DEMO_PASSWORD
from .config import ROOT
from .main import app

LATENCY_TARGET_MS = 500        # warm, generous vs the 300ms architecture goal

# S1 story geography (see exports/stories.json): 3 Belagavi + 2 Davanagere +
# 6 Dharwad cases. Expected visible-case counts per rank:
S1_TOTAL, S1_NORTHERN_RANGE, S1_DHARWAD = 11, 9, 6


def main():
    client = TestClient(app)
    stories = json.loads((ROOT / "exports" / "stories.json").read_text())
    failures, timings = [], {}

    def login(username):
        r = client.post("/api/auth/login",
                        json={"username": username, "password": DEMO_PASSWORD})
        assert r.status_code == 200, f"login {username}: {r.text}"
        return {"Authorization": f"Bearer {r.json()['token']}"}

    H = {u: login(u) for u in
         ("dgp", "scrb", "dig.northern", "sp.belagavi", "sp.davanagere",
          "sp.dharwad", "io.market", "io.davanagere", "io.hubballi")}

    def get(path, label=None, who="dgp"):
        client.get(path, headers=H[who])       # warm
        t0 = time.perf_counter()
        r = client.get(path, headers=H[who])
        ms = (time.perf_counter() - t0) * 1000
        timings[label or path] = round(ms, 1)
        return r

    def check(label, ok, detail=""):
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              + (f": {detail}" if detail != "" else ""))
        if not ok:
            failures.append(label)

    r = get("/api/health")
    check("health", r.status_code == 200 and r.json()["ok"], r.json())

    r = get("/api/meta")
    check("meta: 31 districts with coordinates",
          len(r.json()["districts"]) == 31)

    r = get("/api/kpis")
    k = r.json()
    check("kpis: all headline fields present incl. property recovery",
          all(k.get(f) is not None for f in
              ("cases_last_30d", "open_investigations", "chargesheet_rate_pct",
               "active_alerts", "repeat_offender_entities",
               "property_recovery_pct"))
          and 0 < k["property_recovery_pct"] < 100, k)

    r = get("/api/map/districts")
    check("map/districts: 31 rows, all with cases",
          len(r.json()["districts"]) == 31
          and all(d["n"] > 0 for d in r.json()["districts"]))
    dharwad = next(d for d in r.json()["districts"] if d["name"] == "Dharwad")
    flagged = [d for d in r.json()["districts"] if d["has_spike_alert"]]
    check("map/districts: all-heads spike flags stay a top-6 subset",
          1 <= len(flagged) <= 6, len(flagged))
    # Dharwad's spikes are real but below the statewide top-6 (2026-07-02 map
    # bugfix decision); it flags under its crime-head filter (5 = Crimes
    # Against Women, z=5.0) and inside its own jurisdiction's top-6.
    r = get("/api/map/districts?head_id=5", "/api/map/districts+head")
    dh = next(d for d in r.json()["districts"] if d["name"] == "Dharwad")
    check("map/districts: Dharwad flags under its crime-head filter, "
          "spike names its crime",
          dh["has_spike_alert"] and dh["spike_z"] >= 2
          and "Dharwad" in (dh["spike_summary"] or ""))

    r = get(f"/api/map/stations?district_id={dharwad['district_id']}",
            "/api/map/stations")
    check("map/stations: Dharwad stations with coords",
          len(r.json()["stations"]) > 20)

    r = get(f"/api/map/stations?district_id={dharwad['district_id']}"
            f"&hour_band=06-09", "/api/map/stations+hourband")
    check("map/stations: hour-band filter works",
          sum(s["n"] for s in r.json()["stations"]) > 0)

    all_n = sum(d["n"] for d in get("/api/map/districts").json()["districts"])
    r = get("/api/map/districts?hour_band=00-03",
            "/api/map/districts+hourband")
    night = sum(d["n"] for d in r.json()["districts"])
    check("map/districts: hour-band layer works at STATE level "
          "(spatiotemporal requirement)",
          0 < night < all_n * 0.1, f"{night} of {all_n} in 00-03")
    check("map/districts: hour view claims NO spike flags (spikes are "
          "daily-volume signals; a 0-case view must never pulse red)",
          not any(d["has_spike_alert"] for d in r.json()["districts"]))

    r = get("/api/alerts?kind=spike")
    snatch = [a for a in r.json()["alerts"]
              if "two-wheeler-pillion-snatch" in a["summary"]
              and a["scope_id"] == dharwad["district_id"]]
    check("alerts: Dharwad snatching pattern spike with evidence",
          bool(snatch) and len(snatch[0]["evidence"]) >= 4,
          snatch[0]["summary"] if snatch else "missing")

    # ---- the demo pivot: search -> entity -> network -> case ---------------
    r = get("/api/search?q=Ravikumar")
    hits = [e for e in r.json()["entities"] if e["n_cases"] >= 10]
    check("search: 'Ravikumar' surfaces the serial snatcher", bool(hits))
    eid = None
    if hits:
        eid = hits[0]["entity_id"]
        r = get(f"/api/entities/{eid}", "/api/entities/{id}")
        e = r.json()
        check("entity: 11 cases, 3+ aliases, risk factors, captured IDs",
              e["n_cases"] == S1_TOTAL and len(e["aliases"]) >= 3
              and e["risk_factors"] and len(e["captured_ids"]) >= 2)
        check("entity: same aadhaar visible on both arrest captures",
              len({i["id_value"] for i in e["captured_ids"]
                   if i["id_type"] == "aadhaar"}) == 1)
        check("entity: evidence carries all case CrimeNos",
              len(e["evidence"]) == S1_TOTAL)
        crime_no = e["cases"][0]["crime_no"]
        r = get(f"/api/cases/{crime_no}", "/api/cases/{crime_no}")
        c = r.json()
        check("case detail: sections+parties+MO+similar cases",
              c["sections"] and c["accused"] and c["mo_tags"]
              and len(c["similar_cases"]) >= 1)

    fence_pid = stories["S2_vehicle_ring"]["fence_pid"]
    r = get("/api/search?q=Salim Mujawar")
    fence_hits = [e for e in r.json()["entities"] if e["n_cases"] == 4]
    check("search: the S2 fence is findable", bool(fence_hits))
    if fence_hits:
        r = get(f"/api/network/entity/{fence_hits[0]['entity_id']}",
                "/api/network/entity/{id}")
        g = r.json()
        check("network: fence ego graph has 5+ nodes, evidence on edges",
              len(g["nodes"]) >= 5
              and all(ed["evidence"] for ed in g["edges"]))

    r = get("/api/network/top")
    groups = r.json()["groups"]
    check("network/top: discovery leaderboard of connected groups",
          len(groups) >= 8 and all(g["degree"] >= 2 for g in groups)
          and groups == sorted(groups, key=lambda g: -g["degree"]),
          f"top degree {groups[0]['degree']}" if groups else "empty")
    r = get(f"/api/network/entity/{groups[0]['entity_id']}",
            "/api/network/entity/top1", who="sp.dharwad")
    check("network/top: #1 group's graph opens for a scoped SP (identity "
          "intel is statewide)",
          r.status_code == 200 and len(r.json()["nodes"]) >= 3)

    r = get("/api/trends?months=24")
    check("trends: 24 monthly points + baseline",
          len(r.json()["series"]) == 24 and r.json()["monthly_baseline"] > 0)

    r = get("/api/er/metrics")
    check("er/metrics: honesty endpoint serves precision/recall",
          r.json().get("er_precision", 0) >= 0.9)

    # ---- Phase 5: RBAC by rank ---------------------------------------------
    print("  ---- RBAC ----")
    r = client.get("/api/kpis")
    check("rbac: no token -> 401", r.status_code == 401)
    r = client.post("/api/auth/login",
                    json={"username": "dgp", "password": "wrong"})
    check("rbac: wrong password -> 401", r.status_code == 401)

    for who, n in (("dig.northern", 5), ("sp.dharwad", 1)):
        r = get("/api/map/districts", f"map as {who}", who=who)
        check(f"rbac: {who} map shows {n} district(s)",
              len(r.json()["districts"]) == n,
              [d["name"] for d in r.json()["districts"]])

    if eid:
        # Graduated disclosure: every rank sees ALL linked case numbers
        # (the full linkage picture); what varies is how many are flagged
        # restricted (party details held by the owning jurisdiction).
        for who, in_scope in (("dig.northern", S1_NORTHERN_RANGE),
                              ("sp.belagavi", 3),
                              ("sp.davanagere", 2),
                              ("sp.dharwad", S1_DHARWAD),
                              ("io.market", 3),        # all 3 at Market PS
                              ("io.davanagere", 2),    # both at Dav. Town PS
                              ("io.hubballi", S1_DHARWAD)):
            e = get(f"/api/entities/{eid}", f"entity as {who}", who=who).json()
            check(f"rbac: S1 profile as {who}: all {S1_TOTAL} case numbers, "
                  f"{S1_TOTAL - in_scope} marked restricted",
                  len(e["cases"]) == S1_TOTAL
                  and sum(c["restricted"] for c in e["cases"])
                      == S1_TOTAL - in_scope
                  and e["cases_outside_scope"] == S1_TOTAL - in_scope
                  and len(e["aliases"]) >= 3)     # identity intel statewide
        e = get(f"/api/entities/{eid}", "entity aadhaar as sp",
                who="sp.dharwad").json()
        check("rbac: SP still sees the cross-district aadhaar identity link",
              len({i["id_value"] for i in e["captured_ids"]
                   if i["id_type"] == "aadhaar"}) == 1
              and len(e["captured_ids"]) >= 2)

    belagavi_fir = stories["S1_serial_snatcher"]["cases"][0]
    r = client.get(f"/api/cases/{belagavi_fir}", headers=H["sp.dharwad"])
    rc = r.json()
    check("rbac: SP Dharwad opening a Belagavi FIR -> RESTRICTED view "
          "(structure yes, parties/narrative no)",
          r.status_code == 200 and rc["access"] == "restricted"
          and rc["BriefFacts"] is None and not rc["victims"]
          and not rc["captured_ids"] and rc["sections"] and rc["mo_tags"]
          and rc["redacted"]["victims"] >= 1
          and "Request access" in rc["restriction_note"])
    r = client.post(f"/api/cases/{belagavi_fir}/request-access",
                    headers=H["sp.dharwad"])
    check("rbac: access request recorded", r.status_code == 200
          and r.json()["ok"])
    r = client.get(f"/api/cases/{belagavi_fir}", headers=H["dig.northern"])
    check("rbac: DIG Northern (Belagavi in range) gets the FULL record",
          r.status_code == 200 and r.json()["access"] == "full"
          and r.json()["victims"])

    cl = get("/api/cases", "cases as io", who="io.hubballi").json()["cases"]
    check("rbac: IO case list pinned to Hubballi Town PS",
          cl and {x["station"] for x in cl} == {"Hubballi Town PS"})
    r = client.get("/api/cases?district_id=1003", headers=H["sp.dharwad"])
    check("rbac: SP requesting another district's list -> 403",
          r.status_code == 403)

    r = get("/api/kpis", "kpis as io", who="io.hubballi")
    check("rbac: IO KPIs are station-level (subset of district)",
          r.json()["cases_last_30d"] < k["cases_last_30d"])
    r = get(f"/api/map/stations?district_id={dharwad['district_id']}",
            "map/stations as io", who="io.hubballi")
    st = r.json()["stations"]
    check("rbac: IO station layer shows ONLY their own station",
          len(st) == 1 and st[0]["name"] == "Hubballi Town PS",
          [s["name"] for s in st])

    r = client.get("/api/audit", headers=H["sp.dharwad"])
    check("rbac: audit trail denied below state level", r.status_code == 403)
    r = get("/api/audit?limit=200", "/api/audit")
    entries = r.json()["entries"]
    events = {e["event"] for e in entries}
    denied = [e for e in entries if e["event"] == "access-denied"]
    check("audit: semantic trail — sign-ins, searches, record access, "
          "access requests, denials",
          {"login", "search", "profile-view", "case-view", "access-request"}
          <= events
          and len(denied) >= 2
          and any(e["user"] == "sp.dharwad" for e in denied),
          f"{len(entries)} entries, {len(denied)} denials, events={sorted(events)}")
    check("audit: it is a trail of actions, not a request log "
          "(no dashboard noise)",
          not any(e["event"].startswith(("GET ", "POST ")) for e in entries))

    slow = {k_: v for k_, v in timings.items() if v > LATENCY_TARGET_MS}
    check(f"latency: all endpoints < {LATENCY_TARGET_MS}ms warm",
          not slow, slow or f"max {max(timings.values())}ms")
    print("  timings(ms):", dict(sorted(timings.items(), key=lambda kv: -kv[1])))

    print("APICHECK:", "ALL PASS" if not failures else f"FAILURES: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
