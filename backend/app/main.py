"""DRISHTI API — serves the five lenses over the precomputed intelligence.

Evidence doctrine: every endpoint that makes a CLAIM (an alert, a profile, a
trend spike, a network edge, a case link) returns the CrimeNos behind it.
Aggregate/navigation endpoints (map counts) return counts plus the drill-down
path that leads to the underlying cases — nothing is more than two clicks from
its FIRs.

Access doctrine (Phase 5, enforced here on every endpoint via auth.py):
- CASE RECORDS are jurisdiction-scoped by rank (state / range / district /
  station). Out-of-scope case detail returns 403 with a human explanation.
- IDENTITY INTELLIGENCE (entities, aliases, risk, network) is statewide
  shared intel; entity profiles filter their case lists to the viewer's
  jurisdiction and report how many cases sit outside it.
- Every request is written to the audit trail (x_audit_log).

In production the backend also serves the built frontend (frontend/dist), so
one container is the whole deployment.

Run (from backend/):   ../.venv/bin/uvicorn app.main:app --port 8000
"""

import datetime as dt
import json
import os
import sqlite3
import statistics
import time
from collections import deque
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth import (AUDIT, DEMO_PASSWORD, DEMO_USERS, User, current_user,
                   ensure_seeded, mint_token, token_user, verify_password)
from .config import AS_OF, DB_PATH, ROOT

app = FastAPI(title="DRISHTI API", version="0.2.0")

# CORS: the production single container serves the UI same-origin (no CORS
# needed); split dev runs the frontend on :5173. Configurable allow-list, not a
# wildcard, so a stray origin can't call the API with a captured token.
_CORS = os.environ.get("DRISHTI_CORS_ORIGINS",
                       "http://localhost:5173,http://127.0.0.1:5173")
app.add_middleware(CORSMiddleware,
                   allow_origins=[o.strip() for o in _CORS.split(",") if o.strip()],
                   allow_methods=["*"], allow_headers=["*"])
# Map/meta payloads are large, repetitive JSON — gzip cuts them ~85%. BUT
# Catalyst AppSail's edge proxy already compresses responses; adding a second
# app-level gzip double-encodes the body, and browsers fail it with
# net::ERR_CONTENT_DECODING_FAILED (curl, sending only `Accept-Encoding: gzip`,
# is unaffected — which masks it). So compress at the app ONLY when NOT behind
# the Catalyst proxy (standalone Docker / local dev); on AppSail the edge does it.
if not os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT"):
    app.add_middleware(GZipMiddleware, minimum_size=1500)

# Per-IP sliding-window rate limiting on the expensive/abusable endpoints:
# login runs 120k-round PBKDF2 (CPU-DoS) and the LLM endpoints cost real money.
# Single process, so an in-memory window suffices. DRISHTI_RATELIMIT=0 disables
# it (the test harness sets this). Every response also gets baseline security
# headers.
_RL_RULES = {"/api/auth/login": (30, 60), "/api/chat": (30, 60),
             "/api/brief": (20, 60)}
_RL: dict[tuple, deque] = {}
_SEC_HEADERS = {"X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"}


@app.middleware("http")
async def guard(request: Request, call_next):
    rule = _RL_RULES.get(request.url.path)
    if rule and os.environ.get("DRISHTI_RATELIMIT", "1") != "0":
        limit, window = rule
        ip = request.client.host if request.client else "?"
        now = time.time()
        dq = _RL.setdefault((request.url.path, ip), deque())
        while dq and dq[0] < now - window:
            dq.popleft()
        if len(dq) >= limit:
            return JSONResponse({"detail": "Too many requests — slow down."},
                                status_code=429)
        dq.append(now)
    resp = await call_next(request)
    for k, v in _SEC_HEADERS.items():
        resp.headers.setdefault(k, v)
    return resp


EVIDENCE_CAP = 50


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def crime_nos(conn, case_ids: list[int]) -> list[str]:
    if not case_ids:
        return []
    marks = ",".join(str(int(i)) for i in case_ids[:EVIDENCE_CAP])
    return [r[0] for r in conn.execute(
        f"SELECT CrimeNo FROM CaseMaster WHERE CaseMasterID IN ({marks})")]


def _window(date_from: str | None, date_to: str | None) -> tuple[str, str]:
    return (date_from or "2021-01-01", date_to or AS_OF)


# -------------------------------------------------------------- scope tools --

def scoped_districts(user: User, requested: int | None = None) -> list[int] | None:
    """The district set this request may touch. None = statewide (no filter).
    Asking for a district outside the caller's jurisdiction is a 403 — access
    control by navigation-hiding alone is not access control."""
    if user.district_ids is None:
        return [int(requested)] if requested else None
    if requested is not None:
        if int(requested) not in user.district_ids:
            raise HTTPException(
                403, f"District {requested} is outside your jurisdiction "
                     f"({user.label})")
        return [int(requested)]
    return list(user.district_ids)


def sqlin(ids: list[int]) -> tuple[str, list[int]]:
    return ",".join("?" * len(ids)), [int(i) for i in ids]


def case_scope_sql(user: User, dids: list[int] | None,
                   unit_alias: str = "u", case_alias: str = "c"
                   ) -> tuple[str, list]:
    """WHERE fragment limiting case rows to the caller's jurisdiction.
    Station IOs are pinned to their station; others to their district set."""
    if user.station_id:
        return f" AND {case_alias}.PoliceStationID=?", [user.station_id]
    if dids is None:
        return "", []
    m, args = sqlin(dids)
    return f" AND {unit_alias}.DistrictID IN ({m})", args


def alert_scope_sql(user: User, dids: list[int] | None) -> tuple[str, list]:
    """Alert visibility: state-level alerts for everyone (statewide context),
    district alerts inside the caller's district set, station alerts for the
    IO's own station or for stations inside the district set."""
    if dids is None:
        return "", []
    m, args = sqlin(dids)
    if user.station_id:
        return (f" AND (scope_type='state' OR (scope_type='district' AND "
                f"scope_id IN ({m})) OR (scope_type='station' AND scope_id=?))",
                args + [user.station_id])
    return (f" AND (scope_type='state' OR (scope_type='district' AND "
            f"scope_id IN ({m})) OR (scope_type='station' AND scope_id IN "
            f"(SELECT UnitID FROM Unit WHERE DistrictID IN ({m}))))",
            args + args)


# ---------------------------------------------------------- query-result cache --
# The analytical tables (x_agg_daily, x_alert, CaseMaster, x_property, x_entity)
# are STATIC between datagen runs — only x_app_user/x_audit_log are written at
# runtime, and no analytical endpoint reads those. So the expensive per-request
# aggregations (kpis, trends, alerts) can be memoized in-process. The key MUST
# carry the caller's scope so one rank never serves another's data from cache.
# FIFO-bounded; the process (hence cache) resets on every redeploy.
_QCACHE: dict = {}
_QCACHE_MAX = 512


def _scope_key(user: User) -> tuple:
    return (user.station_id,
            tuple(sorted(user.district_ids)) if user.district_ids is not None
            else None)


def _cache_get(key):
    return _QCACHE.get(key)


def _cache_put(key, val):
    _QCACHE[key] = val
    if len(_QCACHE) > _QCACHE_MAX:
        del _QCACHE[next(iter(_QCACHE))]
    return val


# -------------------------------------------------------------------- audit --
# The trail records SENSITIVE ACTIONS, not HTTP traffic: record access
# (search / profile / FIR / network / case lists), AI usage (chat / brief),
# sign-ins, and every denial. Dashboard aggregates are not audited —
# see AuditSink's docstring for the doctrine.

@app.exception_handler(StarletteHTTPException)
async def audit_denials(request: Request, exc: StarletteHTTPException):
    # Central choke point: every 403 — whichever endpoint raised it — lands
    # in the trail with its human-readable reason. Denials ARE the proof
    # that enforcement works.
    if exc.status_code == 403 and request.url.path.startswith("/api"):
        tok = (request.headers.get("authorization") or "")
        AUDIT.write(token_user(tok.removeprefix("Bearer ").strip()),
                    "access-denied",
                    {"summary": f"{str(exc.detail)[:280]} "
                                f"[{request.url.path}]"})
    return await http_exception_handler(request, exc)


@app.get("/api/audit")
def audit_trail(limit: int = Query(100, le=500),
                user: User = Depends(current_user)):
    if user.scope_type != "state":
        raise HTTPException(403, "The audit trail is restricted to state-"
                                 "level roles (DGP / SCRB)")
    return {"entries": AUDIT.recent(limit)}


# --------------------------------------------------------------------- auth --

@app.post("/api/auth/login")
def login(body: dict):
    username = (body.get("username") or "").strip().lower()
    user = verify_password(username, body.get("password") or "")
    AUDIT.write(user, "login" if user else "login-failed",
                {"summary": "signed in" if user
                            else f"failed sign-in as '{username[:40]}'"})
    if not user:
        raise HTTPException(401, "Invalid username or password")
    return {"token": mint_token(user.user_id), "user": user.public()}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return user.public()


@app.get("/api/auth/demo")
def demo_accounts():
    """The demo roster for the login screen. Publishing credentials is fine —
    and intended — because every byte of data is synthetic; judges must be
    able to walk the rank ladder in one click each."""
    ensure_seeded()
    accounts = []
    for username, _rid, _sid in DEMO_USERS:
        row = verify_password(username, DEMO_PASSWORD)
        if row:
            accounts.append({"username": username, "label": row.label,
                             "role": row.role})
    return {"accounts": accounts, "password": DEMO_PASSWORD}


# --------------------------------------------------------------------- meta --

@app.get("/api/health")
def health():
    conn = db()
    out = {"ok": True, "as_of": AS_OF,
           "cases": conn.execute("SELECT COUNT(*) FROM CaseMaster").fetchone()[0],
           "entities": conn.execute("SELECT COUNT(*) FROM x_entity").fetchone()[0],
           "alerts": conn.execute("SELECT COUNT(*) FROM x_alert").fetchone()[0]}
    conn.close()
    return out


_META_CACHE: dict | None = None


def _meta_base() -> dict:
    # The reference tables never change at serve time — compute once.
    global _META_CACHE
    if _META_CACHE is None:
        conn = db()
        _META_CACHE = {
            "districts": rows(conn.execute(
                "SELECT d.DistrictID AS id, d.DistrictName AS name, "
                "i.pop_estimate, i.urban_pct, i.literacy_pct, "
                "AVG(g.latitude) AS lat, AVG(g.longitude) AS lon "
                "FROM District d "
                "JOIN x_district_indicators i ON i.district_id=d.DistrictID "
                "JOIN Unit u ON u.DistrictID=d.DistrictID AND u.TypeID>=5 "
                "JOIN x_unit_geo g ON g.UnitID=u.UnitID GROUP BY d.DistrictID")),
            "heads": rows(conn.execute(
                "SELECT CrimeHeadID AS id, CrimeGroupName AS name FROM CrimeHead")),
            "subheads": rows(conn.execute(
                "SELECT CrimeSubHeadID AS id, CrimeHeadID AS head_id, "
                "CrimeHeadName AS name FROM CrimeSubHead")),
        }
        conn.close()
    return _META_CACHE


@app.get("/api/meta")
def meta(user: User = Depends(current_user)):
    base = _meta_base()
    districts = base["districts"]
    if user.district_ids is not None:
        districts = [d for d in districts if d["id"] in user.district_ids]
    return {"as_of": AS_OF, "districts": districts, "heads": base["heads"],
            "subheads": base["subheads"], "scope": user.public()}


# --------------------------------------------------------------------- kpis --

@app.get("/api/kpis")
def kpis(district_id: int | None = None, user: User = Depends(current_user)):
    dids = scoped_districts(user, district_id)
    key = ("kpis", _scope_key(user), district_id)
    hit = _cache_get(key)
    if hit is not None:
        return hit
    conn = db()
    as_of = dt.date.fromisoformat(AS_OF)
    d30 = (as_of - dt.timedelta(days=29)).isoformat()
    prev_from = (as_of - dt.timedelta(days=394)).isoformat()
    prev_to = (as_of - dt.timedelta(days=365)).isoformat()

    if user.station_id:                       # IO: their station's rollups
        agg_scope, agg_args = " AND unit_id=?", [user.station_id]
    elif dids:
        m, agg_args = sqlin(dids)
        agg_scope = f" AND district_id IN ({m})"
    else:
        agg_scope, agg_args = "", []
    cscope, cargs = case_scope_sql(user, dids)

    cur30 = conn.execute(f"SELECT COALESCE(SUM(n),0) FROM x_agg_daily "
                         f"WHERE date>=? {agg_scope}",
                         [d30] + agg_args).fetchone()[0]
    prev30 = conn.execute(f"SELECT COALESCE(SUM(n),0) FROM x_agg_daily "
                          f"WHERE date>=? AND date<=? {agg_scope}",
                          [prev_from, prev_to] + agg_args).fetchone()[0]
    open_cases = conn.execute(
        f"SELECT COUNT(*) FROM CaseMaster c JOIN Unit u ON "
        f"u.UnitID=c.PoliceStationID WHERE c.CaseStatusID=1 {cscope}",
        cargs).fetchone()[0]
    cs = conn.execute(
        f"SELECT AVG(CASE WHEN s.cstype='A' THEN 100.0 ELSE 0 END), "
        f"COUNT(*) FROM ChargesheetDetails s JOIN CaseMaster c ON "
        f"c.CaseMasterID=s.CaseMasterID JOIN Unit u ON "
        f"u.UnitID=c.PoliceStationID WHERE 1=1 {cscope}", cargs).fetchone()
    days = [r[0] for r in conn.execute(
        f"SELECT CAST(julianday(s.csdate)-julianday(c.CrimeRegisteredDate) "
        f"AS INT) FROM ChargesheetDetails s JOIN CaseMaster c ON "
        f"c.CaseMasterID=s.CaseMasterID JOIN Unit u ON "
        f"u.UnitID=c.PoliceStationID WHERE s.cstype='A' {cscope}", cargs)]
    ascope, aargs = alert_scope_sql(user, dids)
    alerts_n = conn.execute(
        f"SELECT COUNT(*) FROM x_alert WHERE 1=1 {ascope}",
        aargs).fetchone()[0]
    if dids:
        m, eargs = sqlin(dids)
        escope = f" AND home_district_id IN ({m})"
    else:
        escope, eargs = "", []
    repeat = conn.execute(
        f"SELECT COUNT(*) FROM x_entity WHERE n_cases>=2 {escope}",
        eargs).fetchone()[0]
    # Property recovery, value-weighted — the classic KSP performance metric
    # ("Crime in Karnataka" publishes stolen-vs-recovered); property offences
    # carry most of the volume, so the strip needs a money number.
    prop = conn.execute(
        f"SELECT SUM(p.value_inr), SUM(CASE WHEN p.recovered=1 THEN "
        f"p.value_inr ELSE 0 END) FROM x_property p "
        f"JOIN CaseMaster c ON c.CaseMasterID=p.CaseMasterID "
        f"JOIN Unit u ON u.UnitID=c.PoliceStationID WHERE 1=1 {cscope}",
        cargs).fetchone()
    conn.close()
    return _cache_put(key, {
        "cases_last_30d": cur30,
        "yoy_change_pct": round(100 * (cur30 - prev30) / prev30, 1) if prev30 else None,
        "open_investigations": open_cases,
        "chargesheet_rate_pct": round(cs[0], 1) if cs[1] else None,
        "median_days_to_chargesheet": statistics.median(days) if days else None,
        "active_alerts": alerts_n,
        "repeat_offender_entities": repeat,
        "property_recovery_pct": round(100 * prop[1] / prop[0], 1)
                                 if prop and prop[0] else None,
        "scope_label": user.label,
    })


# ---------------------------------------------------------------------- map --

@app.get("/api/map/districts")
def map_districts(head_id: int | None = None, hour_band: str | None = None,
                  date_from: str | None = None, date_to: str | None = None,
                  user: User = Depends(current_user)):
    dids = scoped_districts(user)
    conn = db()
    f, t = _window(date_from, date_to)
    dwhere, dargs = "", []
    if dids:
        m, dargs = sqlin(dids)
        dwhere = f"WHERE d.DistrictID IN ({m})"
    if hour_band:
        # The spatiotemporal layer at STATE level ("crime map of Karnataka
        # between 21-24 hrs"). The daily rollup has no hour dimension, so
        # this counts straight off CaseMaster x Inv_OccuranceTime — fine at
        # 200k rows with idx_occtime_case.
        hh = "AND c.CrimeMajorHeadID=? " if head_id else ""
        args = [f, t, hour_band] + ([head_id] if head_id else [])
        data = rows(conn.execute(
            f"SELECT d.DistrictID AS district_id, d.DistrictName AS name, "
            f"COALESCE(x.n,0) AS n, i.pop_estimate, "
            f"ROUND(100000.0*COALESCE(x.n,0)/i.pop_estimate, 1) AS rate_per_lakh "
            f"FROM District d "
            f"JOIN x_district_indicators i ON i.district_id=d.DistrictID "
            f"LEFT JOIN (SELECT u.DistrictID AS did, COUNT(*) AS n "
            f"           FROM CaseMaster c "
            f"           JOIN Unit u ON u.UnitID=c.PoliceStationID "
            f"           JOIN Inv_OccuranceTime o ON o.CaseMasterID=c.CaseMasterID "
            f"           WHERE c.CrimeRegisteredDate>=? AND c.CrimeRegisteredDate<=? "
            f"           AND o.OccurrenceHourBand=? {hh}"
            f"           GROUP BY u.DistrictID) x ON x.did=d.DistrictID "
            f"{dwhere}", args + dargs))
    else:
        hscope = "AND a.crime_head_id=?" if head_id else ""
        args = [f, t] + ([head_id] if head_id else [])
        data = rows(conn.execute(
            f"SELECT d.DistrictID AS district_id, d.DistrictName AS name, "
            f"COALESCE(SUM(a.n),0) AS n, i.pop_estimate, "
            f"ROUND(100000.0*COALESCE(SUM(a.n),0)/i.pop_estimate, 1) AS rate_per_lakh "
            f"FROM District d "
            f"JOIN x_district_indicators i ON i.district_id=d.DistrictID "
            f"LEFT JOIN x_agg_daily a ON a.district_id=d.DistrictID "
            f"AND a.date>=? AND a.date<=? {hscope} "
            f"{dwhere} GROUP BY d.DistrictID", args + dargs))

    # Spike flag honours the crime-head filter and stays a MEANINGFUL subset.
    # Almost every district has *some* spike (301 across 31), so flagging all
    # is noise. With a head selected -> flag districts with a spike in that
    # head; with "all heads" -> flag only the 6 hottest by peak z-score —
    # both computed inside the caller's jurisdiction. The summary always
    # NAMES the spiking crime/pattern (the UI shows it).
    # Honesty rules: spikes are DAILY-VOLUME signals, so an hour-band view
    # carries no spike flags at all; and a district displaying 0 cases can
    # never be flagged red.
    best = {}
    if not hour_band:
        swhere, sargs = "", []
        if dids:
            m, sargs = sqlin(dids)
            swhere = f"AND scope_id IN ({m}) "
        if head_id:
            for did, z, summ in conn.execute(
                    f"SELECT scope_id, zscore, summary FROM x_alert WHERE "
                    f"kind='spike' AND scope_type='district' AND crime_head_id=? "
                    f"{swhere}ORDER BY zscore DESC", [head_id] + sargs):
                best.setdefault(did, (z, summ))
        else:
            for did, z, summ in conn.execute(
                    f"SELECT scope_id, zscore, summary FROM x_alert WHERE "
                    f"kind='spike' AND scope_type='district' "
                    f"{swhere}ORDER BY zscore DESC LIMIT 6", sargs):
                best.setdefault(did, (z, summ))
    for d in data:
        hit = best.get(d["district_id"]) if d["n"] > 0 else None
        d["has_spike_alert"] = hit is not None
        d["spike_z"] = hit[0] if hit else None
        d["spike_summary"] = hit[1] if hit else None
    conn.close()
    return {"window": [f, t], "districts": data,
            "drill_down": "/api/map/stations?district_id="}


@app.get("/api/map/stations")
def map_stations(district_id: int, head_id: int | None = None,
                 hour_band: str | None = None, date_from: str | None = None,
                 date_to: str | None = None,
                 user: User = Depends(current_user)):
    scoped_districts(user, district_id)        # 403 if outside jurisdiction
    # District TOTALS are handbook-public aggregates, but the station-wise
    # breakdown is internal comparative detail: a station-rank officer sees
    # only their own station's point; SP and above see all stations they
    # command.
    conn = db()
    f, t = _window(date_from, date_to)
    # Count matching cases per station via a correlated subquery — keeps every
    # station on the map (zero-case stations included) with clean filters.
    conds, args = ["c.PoliceStationID=u.UnitID",
                   "c.CrimeRegisteredDate>=?", "c.CrimeRegisteredDate<=?"], [f, t]
    if head_id:
        conds.append("c.CrimeMajorHeadID=?")
        args.append(head_id)
    if hour_band:
        conds.append("EXISTS (SELECT 1 FROM Inv_OccuranceTime o WHERE "
                     "o.CaseMasterID=c.CaseMasterID AND o.OccurrenceHourBand=?)")
        args.append(hour_band)
    stscope, stargs = "", []
    if user.station_id:
        stscope, stargs = " AND u.UnitID=?", [user.station_id]
    data = rows(conn.execute(
        f"SELECT u.UnitID AS unit_id, u.UnitName AS name, g.latitude, "
        f"g.longitude, (SELECT COUNT(*) FROM CaseMaster c WHERE "
        f"{' AND '.join(conds)}) AS n "
        f"FROM Unit u JOIN x_unit_geo g ON g.UnitID=u.UnitID "
        f"WHERE u.DistrictID=? AND u.TypeID>=5{stscope}",
        args + [district_id] + stargs))
    conn.close()
    return {"window": [f, t], "stations": data,
            "drill_down": "/api/cases?station_id="}


# ------------------------------------------------------------------- trends --

@app.get("/api/trends")
def trends(district_id: int | None = None, head_id: int | None = None,
           months: int = 24, user: User = Depends(current_user)):
    dids = scoped_districts(user, district_id)
    key = ("trends", _scope_key(user), district_id, head_id, months)
    hit = _cache_get(key)
    if hit is not None:
        return hit
    conn = db()
    scope, args = "", []
    if user.station_id:
        scope += " AND unit_id=?"
        args.append(user.station_id)
    elif dids:
        m, dargs = sqlin(dids)
        scope += f" AND district_id IN ({m})"
        args += dargs
    if head_id:
        scope += " AND crime_head_id=?"
        args.append(head_id)
    series = rows(conn.execute(
        f"SELECT substr(date,1,7) AS month, SUM(n) AS n FROM x_agg_daily "
        f"WHERE 1=1 {scope} GROUP BY 1 ORDER BY 1", args))[-months:]
    values = [r["n"] for r in series[:-1]]
    baseline = round(statistics.mean(values), 1) if values else 0
    sscope, sargs = "", []
    if dids:
        m, sargs = sqlin(dids)
        sscope = f"AND scope_id IN ({m})"
    spikes = rows(conn.execute(
        f"SELECT summary, window_start, window_end, observed, baseline, zscore "
        f"FROM x_alert WHERE kind='spike' {sscope}", sargs))
    conn.close()
    return _cache_put(key, {"series": series, "monthly_baseline": baseline,
                            "spikes": spikes})


# ------------------------------------------------------------------- alerts --

@app.get("/api/alerts")
def alerts(district_id: int | None = None, kind: str | None = None,
           user: User = Depends(current_user)):
    dids = scoped_districts(user, district_id)
    key = ("alerts", _scope_key(user), district_id, kind)
    hit = _cache_get(key)
    if hit is not None:
        return hit
    conn = db()
    scope, args = alert_scope_sql(user, dids)
    if kind:
        scope += " AND kind=?"
        args = args + [kind]
    data = rows(conn.execute(
        f"SELECT alert_id, kind, scope_type, scope_id, summary, observed, "
        f"baseline, zscore, window_start, window_end, evidence "
        f"FROM x_alert WHERE 1=1 {scope} ORDER BY zscore DESC NULLS LAST",
        args))
    # Resolve evidence CrimeNos for ALL alerts in ONE query (was a query per
    # alert -> ~300 round-trips + a 170 KB payload). The list view shows only a
    # few chips per alert; the true total is preserved in evidence_count.
    LIST_EVIDENCE_CAP = 12
    ev_ids = [json.loads(a.pop("evidence") or "[]") for a in data]
    wanted = {int(i) for ids in ev_ids for i in ids[:LIST_EVIDENCE_CAP]}
    cnmap = {}
    if wanted:
        marks = ",".join(str(i) for i in wanted)
        cnmap = {r["CaseMasterID"]: r["CrimeNo"] for r in conn.execute(
            f"SELECT CaseMasterID, CrimeNo FROM CaseMaster "
            f"WHERE CaseMasterID IN ({marks})")}
    for a, ids in zip(data, ev_ids):
        a["evidence"] = [cnmap[int(i)] for i in ids[:LIST_EVIDENCE_CAP]
                         if int(i) in cnmap]
        a["evidence_count"] = len(ids)
    conn.close()
    return _cache_put(key, {"alerts": data})


# ----------------------------------------------------------------- entities --

@app.get("/api/entities/{entity_id}")
def entity(entity_id: int, user: User = Depends(current_user)):
    dids = scoped_districts(user)
    conn = db()
    e = conn.execute("SELECT * FROM x_entity WHERE entity_id=?",
                     (entity_id,)).fetchone()
    if not e:
        conn.close()
        raise HTTPException(404, "entity not found")
    e = dict(e)
    e["risk_factors"] = json.loads(e["risk_factors"] or "{}")
    # Identity layer is statewide intel: name, aliases, risk, accused ID
    # captures and the LINKED CASE NUMBERS are visible to every rank — an
    # investigator must see the whole linkage picture. Out-of-jurisdiction
    # cases are flagged `restricted`: opening them shows the structural
    # record only (graduated disclosure), never party details.
    aliases = [r[0] for r in conn.execute(
        "SELECT DISTINCT shown_name FROM x_entity_member WHERE entity_id=?",
        (entity_id,))]
    cases = rows(conn.execute(
        "SELECT cm.CrimeNo AS crime_no, cm.CrimeRegisteredDate AS registered, "
        "d.DistrictName AS district, u.UnitName AS station, "
        "sh.CrimeHeadName AS subhead, st.CaseStatusName AS status, "
        "m.shown_name, m.match_basis, "
        "u.DistrictID AS district_id, cm.PoliceStationID AS ps_id "
        "FROM x_entity_member m "
        "JOIN CaseMaster cm ON cm.CaseMasterID=m.CaseMasterID "
        "JOIN Unit u ON u.UnitID=cm.PoliceStationID "
        "JOIN District d ON d.DistrictID=u.DistrictID "
        "LEFT JOIN CrimeSubHead sh ON sh.CrimeSubHeadID=cm.CrimeMinorHeadID "
        "JOIN CaseStatusMaster st ON st.CaseStatusID=cm.CaseStatusID "
        "WHERE m.entity_id=? ORDER BY cm.CrimeRegisteredDate",
        (entity_id,)))
    for cc in cases:
        if user.station_id:
            cc["restricted"] = cc.pop("ps_id") != user.station_id
            cc.pop("district_id")
        elif dids is not None:
            cc["restricted"] = cc.pop("district_id") not in dids
            cc.pop("ps_id")
        else:
            cc["restricted"] = False
            cc.pop("district_id"), cc.pop("ps_id")
    ids = rows(conn.execute(
        "SELECT i.id_type, i.id_value, i.captured_on, cm.CrimeNo AS crime_no "
        "FROM x_identity_capture i "
        "JOIN x_entity_member m ON m.AccusedMasterID=i.source_row_id "
        "JOIN CaseMaster cm ON cm.CaseMasterID=i.CaseMasterID "
        "WHERE i.role='accused' AND m.entity_id=?", (entity_id,)))
    associates = rows(conn.execute(
        "SELECT CASE WHEN src_id=? THEN dst_id ELSE src_id END AS entity_id, "
        "e.canonical_name, e.risk_score, n.edge_type, n.weight "
        "FROM x_network_edge n JOIN x_entity e ON e.entity_id="
        "CASE WHEN n.src_id=? THEN n.dst_id ELSE n.src_id END "
        "WHERE n.src_id=? OR n.dst_id=? ORDER BY n.weight DESC LIMIT 10",
        (entity_id, entity_id, entity_id, entity_id)))
    conn.close()
    n_restricted = sum(1 for cc in cases if cc["restricted"])
    AUDIT.write(user, "profile-view",
                {"summary": f"opened offender profile #{entity_id} · "
                            f"{e['canonical_name']} ({len(cases)} cases, "
                            f"{n_restricted} restricted)"})
    return {**e, "aliases": aliases, "cases": cases, "captured_ids": ids,
            "associates": associates,
            "cases_outside_scope": n_restricted,
            "evidence": [c["crime_no"] for c in cases]}


_NETWORK_TOP_CACHE: list | None = None


@app.get("/api/network/top")
def network_top(user: User = Depends(current_user)):
    """The Network tab's landing view: most-connected offender entities
    (degree = distinct associates), the entry point for association
    discovery when you don't already have a suspect. Identity intelligence
    -> statewide for every rank; computed once (edges are immutable at
    serve time)."""
    global _NETWORK_TOP_CACHE
    if _NETWORK_TOP_CACHE is None:
        conn = db()
        _NETWORK_TOP_CACHE = rows(conn.execute(
            "SELECT e.entity_id, e.canonical_name, e.gender, e.n_cases, "
            "e.risk_score, d.DistrictName AS home_district, "
            "x.degree, x.strength "
            "FROM (SELECT id, COUNT(*) AS degree, SUM(weight) AS strength "
            "      FROM (SELECT src_id AS id, weight FROM x_network_edge "
            "            UNION ALL "
            "            SELECT dst_id AS id, weight FROM x_network_edge) "
            "      GROUP BY id ORDER BY degree DESC, strength DESC LIMIT 12) x "
            "JOIN x_entity e ON e.entity_id=x.id "
            "LEFT JOIN District d ON d.DistrictID=e.home_district_id "
            "ORDER BY x.degree DESC, x.strength DESC"))
        conn.close()
    return {"groups": _NETWORK_TOP_CACHE}


@app.get("/api/network/entity/{entity_id}")
def network(entity_id: int, user: User = Depends(current_user)):
    # Identity layer: the graph (who is connected to whom, and how strongly)
    # is statewide intel. Edge evidence FIR numbers are investigative leads;
    # opening an out-of-scope FIR still 403s at /api/cases/{crime_no}.
    conn = db()
    edges = rows(conn.execute(
        "SELECT src_id, dst_id, edge_type, weight, evidence "
        "FROM x_network_edge WHERE src_id=? OR dst_id=? "
        "ORDER BY weight DESC LIMIT 50", (entity_id, entity_id)))
    node_ids = {entity_id}
    for ed in edges:
        node_ids.update((ed["src_id"], ed["dst_id"]))
        ed["evidence"] = crime_nos(conn, json.loads(ed.pop("evidence") or "[]"))
    marks = ",".join(str(i) for i in node_ids)
    nodes = rows(conn.execute(
        f"SELECT entity_id, canonical_name, gender, n_cases, risk_score, "
        f"home_district_id FROM x_entity WHERE entity_id IN ({marks})"))
    conn.close()
    center = next((n["canonical_name"] for n in nodes
                   if n["entity_id"] == entity_id), f"#{entity_id}")
    AUDIT.write(user, "network-view",
                {"summary": f"viewed association graph of #{entity_id} · "
                            f"{center} ({len(nodes)} entities)"})
    return {"center": entity_id, "nodes": nodes, "edges": edges}


# -------------------------------------------------------------------- cases --

@app.get("/api/cases/{crime_no}")
def case_detail(crime_no: str, user: User = Depends(current_user)):
    conn = db()
    c = conn.execute(
        "SELECT cm.*, u.DistrictID AS district_id, u.UnitName AS station, "
        "d.DistrictName AS district, "
        "h.CrimeGroupName AS head, sh.CrimeHeadName AS subhead, "
        "g.LookupValue AS gravity, st.CaseStatusName AS status, "
        "ct.CourtName AS court, e.FirstName AS io_name "
        "FROM CaseMaster cm "
        "JOIN Unit u ON u.UnitID=cm.PoliceStationID "
        "JOIN District d ON d.DistrictID=u.DistrictID "
        "JOIN CrimeHead h ON h.CrimeHeadID=cm.CrimeMajorHeadID "
        "LEFT JOIN CrimeSubHead sh ON sh.CrimeSubHeadID=cm.CrimeMinorHeadID "
        "JOIN GravityOffence g ON g.GravityOffenceID=cm.GravityOffenceID "
        "JOIN CaseStatusMaster st ON st.CaseStatusID=cm.CaseStatusID "
        "LEFT JOIN Court ct ON ct.CourtID=cm.CourtID "
        "LEFT JOIN Employee e ON e.EmployeeID=cm.PolicePersonID "
        "WHERE cm.CrimeNo=?", (crime_no,)).fetchone()
    if not c:
        conn.close()
        raise HTTPException(404, "case not found")
    c = dict(c)
    # Graduated disclosure (not a hard wall): any officer who FOLLOWS a link
    # to this FIR may see its structural/legal record — number, dates,
    # sections, status, MO, accused identity links. Party details (victims,
    # complainants), the narrative, identifiers and property stay with the
    # owning jurisdiction; a request-access path covers the rest. Bulk
    # BROWSING of another jurisdiction (case lists) remains blocked.
    if user.station_id:
        in_scope = c["PoliceStationID"] == user.station_id
    elif user.district_ids is not None:
        in_scope = c["district_id"] in user.district_ids
    else:
        in_scope = True
    cid = c["CaseMasterID"]
    sub_id = c.get("CrimeMinorHeadID")   # captured before the restricted whitelist strips it
    c["sections"] = rows(conn.execute(
        "SELECT ActID AS act, SectionID AS section FROM ActSectionAssociation "
        "WHERE CaseMasterID=? ORDER BY ActOrderID", (cid,)))
    c["accused"] = rows(conn.execute(
        "SELECT a.AccusedMasterID, a.AccusedName AS name, a.AgeYear AS age, "
        "a.GenderID AS gender, a.PersonID AS ordinal, m.entity_id "
        "FROM Accused a LEFT JOIN x_entity_member m "
        "ON m.AccusedMasterID=a.AccusedMasterID WHERE a.CaseMasterID=?", (cid,)))
    c["arrests"] = rows(conn.execute(
        "SELECT ArrestSurrenderDate AS date, AccusedMasterID FROM "
        "ArrestSurrender WHERE CaseMasterID=?", (cid,)))
    c["chargesheet"] = rows(conn.execute(
        "SELECT csdate AS date, cstype FROM ChargesheetDetails "
        "WHERE CaseMasterID=?", (cid,)))
    c["mo_tags"] = [r[0] for r in conn.execute(
        "SELECT tag FROM x_mo_tag WHERE CaseMasterID=?", (cid,))]
    c["access"] = "full" if in_scope else "restricted"
    if in_scope:
        c["complainants"] = rows(conn.execute(
            "SELECT ComplainantName AS name, AgeYear AS age FROM "
            "ComplainantDetails WHERE CaseMasterID=?", (cid,)))
        c["victims"] = rows(conn.execute(
            "SELECT VictimName AS name, AgeYear AS age, GenderID AS gender "
            "FROM Victim WHERE CaseMasterID=?", (cid,)))
        c["property"] = rows(conn.execute(
            "SELECT kind, description, identifier, value_inr, recovered "
            "FROM x_property WHERE CaseMasterID=?", (cid,)))
        c["captured_ids"] = rows(conn.execute(
            "SELECT role, id_type, id_value FROM x_identity_capture "
            "WHERE CaseMasterID=?", (cid,)))
    else:
        counts = {t: conn.execute(
            f"SELECT COUNT(*) FROM {tbl} WHERE CaseMasterID=?",
            (cid,)).fetchone()[0]
            for t, tbl in (("complainants", "ComplainantDetails"),
                           ("victims", "Victim"),
                           ("property", "x_property"),
                           ("captured_ids", "x_identity_capture"))}
        note = (
            f"Party details, narrative, identifiers and property of this FIR "
            f"are held by {c['station']}, {c['district']} district. Request "
            f"access to view the full record.")
        # SELECT cm.* pulls RAW CaseMaster columns including the incident
        # latitude/longitude — those must not leave the owning jurisdiction.
        # Rebuild the restricted view from a whitelist of structural/legal
        # fields only (number, dates, station, sections, MO, status).
        keep = ("CrimeNo", "IncidentFromDate", "IncidentToDate",
                "InfoReceivedPSDate", "CrimeRegisteredDate", "district_id",
                "station", "district", "head", "subhead", "gravity", "status",
                "court", "io_name", "sections", "accused", "arrests",
                "chargesheet", "mo_tags", "access")
        c = {k: c[k] for k in keep if k in c}
        c["BriefFacts"] = None
        c["complainants"], c["victims"] = [], []
        c["property"], c["captured_ids"] = [], []
        c["redacted"] = counts
        c["restriction_note"] = note
    c["similar_cases"] = rows(conn.execute(
        "SELECT cm2.CrimeNo AS crime_no, cm2.CrimeRegisteredDate AS registered, "
        "d2.DistrictName AS district, COUNT(DISTINCT m2.tag) AS shared_tags "
        "FROM x_mo_tag m1 "
        "JOIN x_mo_tag m2 ON m2.tag=m1.tag AND m2.CaseMasterID!=m1.CaseMasterID "
        "JOIN CaseMaster cm2 ON cm2.CaseMasterID=m2.CaseMasterID "
        "AND cm2.CrimeMinorHeadID=? "
        "JOIN Unit u2 ON u2.UnitID=cm2.PoliceStationID "
        "JOIN District d2 ON d2.DistrictID=u2.DistrictID "
        "WHERE m1.CaseMasterID=? "
        "GROUP BY cm2.CaseMasterID ORDER BY shared_tags DESC, "
        "cm2.CrimeRegisteredDate DESC LIMIT 5",
        (sub_id, cid)))
    conn.close()
    AUDIT.write(user, "case-view",
                {"summary": f"opened FIR {crime_no} ({c['station']}, "
                            f"{c['district']})"
                            + ("" if in_scope else " — RESTRICTED view")})
    return c


@app.post("/api/cases/{crime_no}/request-access")
def request_access(crime_no: str, user: User = Depends(current_user)):
    """The graduated-disclosure escalation path: the request is recorded on
    the audit trail (in production it would also notify the owning SP)."""
    conn = db()
    row = conn.execute(
        "SELECT u.UnitName AS station, d.DistrictName AS district "
        "FROM CaseMaster cm JOIN Unit u ON u.UnitID=cm.PoliceStationID "
        "JOIN District d ON d.DistrictID=u.DistrictID WHERE cm.CrimeNo=?",
        (crime_no,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "case not found")
    AUDIT.write(user, "access-request",
                {"summary": f"requested full access to FIR {crime_no} "
                            f"({row['station']}, {row['district']})"})
    return {"ok": True,
            "message": f"Access request recorded on the audit trail — in "
                       f"production it is routed to the SP, "
                       f"{row['district']} district, for approval."}


@app.get("/api/cases")
def case_list(station_id: int | None = None, district_id: int | None = None,
              head_id: int | None = None, date_from: str | None = None,
              date_to: str | None = None, limit: int = Query(50, le=200),
              user: User = Depends(current_user)):
    dids = scoped_districts(user, district_id)
    if user.station_id:
        if station_id and station_id != user.station_id:
            raise HTTPException(
                403, f"That station is outside your jurisdiction "
                     f"({user.label}).")
        station_id = user.station_id
    conn = db()
    f, t = _window(date_from, date_to)
    scope, args = "", [f, t]
    if station_id:
        scope += " AND cm.PoliceStationID=?"
        args.append(station_id)
    elif dids:
        m, dargs = sqlin(dids)
        scope += f" AND u.DistrictID IN ({m})"
        args += dargs
    if head_id:
        scope += " AND cm.CrimeMajorHeadID=?"
        args.append(head_id)
    data = rows(conn.execute(
        f"SELECT cm.CrimeNo AS crime_no, cm.CrimeRegisteredDate AS registered, "
        f"u.UnitName AS station, sh.CrimeHeadName AS subhead, "
        f"st.CaseStatusName AS status "
        f"FROM CaseMaster cm JOIN Unit u ON u.UnitID=cm.PoliceStationID "
        f"LEFT JOIN CrimeSubHead sh ON sh.CrimeSubHeadID=cm.CrimeMinorHeadID "
        f"JOIN CaseStatusMaster st ON st.CaseStatusID=cm.CaseStatusID "
        f"WHERE cm.CrimeRegisteredDate>=? AND cm.CrimeRegisteredDate<=? "
        f"{scope} ORDER BY cm.CrimeRegisteredDate DESC LIMIT ?",
        args + [limit]))
    conn.close()
    filt = [w for w in (f"station {station_id}" if station_id else None,
                        f"district {district_id}" if district_id else None,
                        f"head {head_id}" if head_id else None) if w]
    AUDIT.write(user, "case-list",
                {"summary": f"browsed case records "
                            f"({', '.join(filt) or 'jurisdiction-wide'}; "
                            f"{len(data)} rows)"})
    return {"window": [f, t], "cases": data}


# ------------------------------------------------------------------- search --

@app.get("/api/search")
def search(q: str = Query(min_length=2), user: User = Depends(current_user)):
    dids = scoped_districts(user)
    conn = db()
    like = f"%{q}%"
    # Entities are statewide identity intel by doctrine — a Dharwad SP must
    # be able to ask "is this name known anywhere in Karnataka?". Their case
    # drill-down stays scoped. CrimeNo search only returns in-scope FIRs.
    entities = rows(conn.execute(
        "SELECT DISTINCT e.entity_id, e.canonical_name, e.gender, e.n_cases, "
        "e.risk_score, d.DistrictName AS home_district "
        "FROM x_entity e "
        "LEFT JOIN District d ON d.DistrictID=e.home_district_id "
        "WHERE e.entity_id IN (SELECT entity_id FROM x_entity_member "
        "WHERE shown_name LIKE ?) "
        "ORDER BY e.n_cases DESC, e.risk_score DESC LIMIT 10", (like,)))
    cscope, cargs = case_scope_sql(user, dids, unit_alias="u", case_alias="cm")
    cases = rows(conn.execute(
        f"SELECT cm.CrimeNo AS crime_no, cm.CrimeRegisteredDate AS registered "
        f"FROM CaseMaster cm JOIN Unit u ON u.UnitID=cm.PoliceStationID "
        f"WHERE cm.CrimeNo LIKE ? {cscope} LIMIT 10", [q + "%"] + cargs))
    conn.close()
    AUDIT.write(user, "search",
                {"summary": f"searched \"{q[:80]}\" → {len(entities)} "
                            f"persons, {len(cases)} FIRs"})
    return {"entities": entities, "cases": cases}


# --------------------------------------------------------------- er metrics --

@app.get("/api/er/metrics")
def er_metrics(user: User = Depends(current_user)):
    conn = db()
    out = {k: json.loads(v) for k, v in
           conn.execute("SELECT key, value FROM x_metric")}
    conn.close()
    return out


# ------------------------------------------------------- agentic layer (GLM) --

def _chat_scope(user: User) -> dict | None:
    if user.district_ids is None:
        return None
    return {"district_ids": list(user.district_ids),
            "station_id": user.station_id, "label": user.label}


@app.post("/api/chat")
def chat_endpoint(body: dict, user: User = Depends(current_user)):
    """Ask-the-Data agent. Body: {"messages": [{"role","content"}...]}."""
    from .chat import ask
    from .llm.zoho import TokenError, LLMError
    messages = [m for m in body.get("messages", [])
                if m.get("role") in ("user", "assistant") and m.get("content")]
    if not messages:
        raise HTTPException(400, "messages required")
    question = str(messages[-1].get("content", ""))[:160]
    lang = "kn" if str(body.get("lang", "")).lower() in ("kn", "kannada") else "en"
    try:
        out = ask(messages[-8:], scope=_chat_scope(user), lang=lang)
    except TokenError as e:
        AUDIT.write(user, "chat",
                    {"summary": f'asked: "{question}" (LLM unavailable)'})
        raise HTTPException(503, f"LLM credentials not configured: {e}")
    except LLMError:
        AUDIT.write(user, "chat",
                    {"summary": f'asked: "{question}" (LLM error)'})
        raise HTTPException(503, "AI service temporarily unavailable — retry.")
    tools = ", ".join(dict.fromkeys(t["tool"] for t in out.get("trace", []))) \
        or "no tools"
    AUDIT.write(user, "chat",
                {"summary": f'asked: "{question}" → {tools}; '
                            f'{len(out.get("evidence", []))} FIRs cited'})
    return out


@app.post("/api/brief")
def brief_endpoint(body: dict, user: User = Depends(current_user)):
    """Intelligence brief. Body: {"district_id"?} or {"alert_id"?}."""
    from .brief import build_brief
    from .llm.zoho import TokenError, LLMError
    district_id, alert_id = body.get("district_id"), body.get("alert_id")
    if alert_id and not district_id:
        conn = db()
        row = conn.execute("SELECT scope_type, scope_id FROM x_alert WHERE "
                           "alert_id=?", (alert_id,)).fetchone()
        if row and row["scope_type"] == "station":
            district_id = conn.execute(
                "SELECT DistrictID FROM Unit WHERE UnitID=?",
                (row["scope_id"],)).fetchone()[0]
        elif row and row["scope_type"] == "district":
            district_id = row["scope_id"]
        conn.close()
    if user.district_ids is not None:
        if district_id is None:
            if len(user.district_ids) == 1:
                district_id = user.district_ids[0]   # SP/IO: their district
            else:
                raise HTTPException(
                    403, f"Statewide briefs need state-level access; pick a "
                         f"district in your range ({user.label}).")
        elif district_id not in user.district_ids:
            raise HTTPException(
                403, f"That district is outside your jurisdiction "
                     f"({user.label}).")
    try:
        out = build_brief(district_id=district_id, alert_id=alert_id)
    except TokenError as e:
        raise HTTPException(503, f"LLM credentials not configured: {e}")
    except LLMError:
        raise HTTPException(503, "AI service temporarily unavailable — retry.")
    AUDIT.write(user, "brief",
                {"summary": f"generated intelligence brief — "
                            f"{out.get('scope', district_id or 'statewide')}"
                            + (f" (alert {alert_id})" if alert_id else "")})
    return out


# --------------------------------------------------------- startup warm --

@app.on_event("startup")
def _warm_statewide_cache() -> None:
    """Precompute the heavy statewide (DGP) aggregates in a background thread at
    boot, so the FIRST dashboard load is already cached and instant — the common
    demo entry point, and the widest (slowest) scope. Best-effort and fully
    isolated: any failure here is swallowed so it can never stop the app from
    serving, and the daemon thread never blocks startup."""
    import threading

    def _work():
        try:
            ensure_seeded()
            u = verify_password("dgp", DEMO_PASSWORD)
            if u is not None:
                kpis(None, u)
                trends(None, None, 24, u)
                alerts(None, None, u)
        except Exception:
            pass

    threading.Thread(target=_work, daemon=True).start()


# ---------------------------------------------------------------- frontend --

# In production one container serves everything: the built React app is
# mounted last so every /api route above wins first. Hash routing means no
# SPA fallback logic is needed beyond index.html.
STATIC_DIR = Path(os.environ.get("DRISHTI_STATIC", ROOT / "frontend" / "dist"))
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
