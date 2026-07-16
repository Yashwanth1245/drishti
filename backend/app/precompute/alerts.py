"""x_alert: spikes, emerging trends, anomalies — the proactive layer.

  spike           district x crime-subhead: current 90-day window vs the mean
                  of the trailing 8 windows; z >= 2.0 and count >= 4. (This is
                  what fires for the planted Hubballi snatching surge.)
  emerging-trend  statewide subhead volume growing >= 15% YoY on real volume
                  (cyber fraud's genuine year-over-year climb).
  anomaly         serial false complainants (>= 3 B-type final reports),
                  duplicate FIR registrations, chronically slow stations.

Every alert stores observed/baseline/z plus evidence CaseMasterIDs.
"""

import datetime as dt
import json
import statistics
from collections import defaultdict

from ..config import (ANOMALY_FALSE_CASES_MIN, AS_OF, EMERGING_GROWTH,
                      EMERGING_MIN_YEAR_N, SLOW_STATION_MIN_SHEETS,
                      SLOW_STATION_RATIO, SPIKE_BASELINE_WINDOWS,
                      SPIKE_MIN_CURRENT, SPIKE_WINDOW_DAYS, SPIKE_Z)

EVIDENCE_CAP = 30


def build(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM x_alert")
    as_of = dt.date.fromisoformat(AS_OF)
    alert_id = 0
    rows = []

    def add(kind, scope_type, scope_id, head_id, wstart, wend, observed,
            baseline, z, summary, evidence):
        nonlocal alert_id
        alert_id += 1
        rows.append((alert_id, kind, scope_type, scope_id, head_id,
                     wstart, wend, observed, baseline, z, summary,
                     json.dumps(evidence[:EVIDENCE_CAP])))

    names = {
        "district": dict(cur.execute("SELECT DistrictID, DistrictName FROM District")),
        "subhead": dict(cur.execute("SELECT CrimeSubHeadID, CrimeHeadName FROM CrimeSubHead")),
        "unit": dict(cur.execute("SELECT UnitID, UnitName FROM Unit")),
    }
    head_of_sub = dict(cur.execute(
        "SELECT CrimeSubHeadID, CrimeHeadID FROM CrimeSubHead"))

    # ---- spikes: district x subhead, windowed z-score ---------------------
    windows = defaultdict(lambda: defaultdict(int))     # (did, sub) -> widx -> n
    current_cases = defaultdict(list)
    horizon = SPIKE_WINDOW_DAYS * (SPIKE_BASELINE_WINDOWS + 1)
    for cid, date, did, sub in cur.execute(
            "SELECT c.CaseMasterID, c.CrimeRegisteredDate, u.DistrictID, "
            "c.CrimeMinorHeadID FROM CaseMaster c "
            "JOIN Unit u ON u.UnitID=c.PoliceStationID "
            "WHERE c.CrimeMinorHeadID IS NOT NULL"):
        age = (as_of - dt.date.fromisoformat(date)).days
        if age < 0 or age >= horizon:
            continue
        widx = age // SPIKE_WINDOW_DAYS
        windows[(did, sub)][widx] += 1
        if widx == 0:
            current_cases[(did, sub)].append(cid)

    n_spikes = 0
    wstart = (as_of - dt.timedelta(days=SPIKE_WINDOW_DAYS - 1)).isoformat()
    for (did, sub), by_w in windows.items():
        cur_n = by_w.get(0, 0)
        if cur_n < SPIKE_MIN_CURRENT:
            continue
        base = [by_w.get(i, 0) for i in range(1, SPIKE_BASELINE_WINDOWS + 1)]
        mu = statistics.mean(base)
        sigma = max(statistics.pstdev(base), mu ** 0.5, 1.0)
        z = (cur_n - mu) / sigma
        if z < SPIKE_Z:
            continue
        pct = round(100 * (cur_n - mu) / mu) if mu else 100
        add("spike", "district", did, head_of_sub.get(sub),
            wstart, AS_OF, cur_n, round(mu, 1), round(z, 2),
            f"{names['subhead'].get(sub, 'Crime')} in "
            f"{names['district'].get(did, did)} is {pct}% above its "
            f"8-window baseline ({cur_n} vs {mu:.1f} per {SPIKE_WINDOW_DAYS} days)",
            sorted(current_cases[(did, sub)]))
        n_spikes += 1

    # ---- spikes at MO-pattern level -----------------------------------------
    # Categories can hide patterns (4 extra snatchings drown inside the broad
    # robbery/theft volume) — the pattern itself is the police-actionable unit.
    mo_windows = defaultdict(lambda: defaultdict(int))
    mo_current = defaultdict(list)
    total_cases = cur.execute("SELECT COUNT(*) FROM CaseMaster").fetchone()[0]
    common_tags = {t for (t, n) in cur.execute(
        "SELECT tag, COUNT(*) FROM x_mo_tag GROUP BY tag")
        if n / total_cases >= 0.05}          # too generic to alert on
    for cid, date, did, tag in cur.execute(
            "SELECT c.CaseMasterID, c.CrimeRegisteredDate, u.DistrictID, m.tag "
            "FROM x_mo_tag m JOIN CaseMaster c ON c.CaseMasterID=m.CaseMasterID "
            "JOIN Unit u ON u.UnitID=c.PoliceStationID"):
        if tag in common_tags:
            continue
        age = (as_of - dt.date.fromisoformat(date)).days
        if age < 0 or age >= horizon:
            continue
        widx = age // SPIKE_WINDOW_DAYS
        mo_windows[(did, tag)][widx] += 1
        if widx == 0:
            mo_current[(did, tag)].append(cid)
    for (did, tag), by_w in mo_windows.items():
        cur_n = by_w.get(0, 0)
        if cur_n < SPIKE_MIN_CURRENT:
            continue
        base = [by_w.get(i, 0) for i in range(1, SPIKE_BASELINE_WINDOWS + 1)]
        mu = statistics.mean(base)
        sigma = max(statistics.pstdev(base), mu ** 0.5, 1.0)
        z = (cur_n - mu) / sigma
        if z < SPIKE_Z:
            continue
        pct = round(100 * (cur_n - mu) / mu) if mu else 100
        add("spike", "district", did, None, wstart, AS_OF, cur_n,
            round(mu, 1), round(z, 2),
            f"Pattern '{tag}' in {names['district'].get(did, did)} is {pct}% "
            f"above its 8-window baseline ({cur_n} vs {mu:.1f} per "
            f"{SPIKE_WINDOW_DAYS} days)", sorted(mo_current[(did, tag)]))
        n_spikes += 1

    # ---- emerging trends: statewide subhead YoY ----------------------------
    yearly = defaultdict(lambda: defaultdict(int))
    for sub, year, n in cur.execute(
            "SELECT CrimeMinorHeadID, CAST(substr(CrimeRegisteredDate,1,4) AS INT), "
            "COUNT(*) FROM CaseMaster WHERE CrimeMinorHeadID IS NOT NULL "
            "GROUP BY 1, 2"):
        yearly[sub][year] = n
    n_trends = 0
    # Compare the two most recent COMPLETE years, derived from AS_OF so this
    # never goes stale as the data span advances. The current partial year is
    # excluded on purpose — half a year would understate every trend.
    last_year = int(AS_OF[:4]) - 1
    prev_year = last_year - 1
    for sub, by_year in yearly.items():
        prev, last = by_year.get(prev_year, 0), by_year.get(last_year, 0)
        if last < EMERGING_MIN_YEAR_N or prev == 0:
            continue
        growth = (last - prev) / prev
        if growth >= EMERGING_GROWTH:
            evidence = [r[0] for r in cur.execute(
                "SELECT CaseMasterID FROM CaseMaster WHERE CrimeMinorHeadID=? "
                "AND CrimeRegisteredDate >= ? LIMIT ?",
                (sub, f"{last_year}-01-01", EVIDENCE_CAP))]
            add("emerging-trend", "state", 1, head_of_sub.get(sub),
                f"{prev_year}-01-01", AS_OF, last, prev, round(growth, 2),
                f"{names['subhead'].get(sub, 'Crime')} rose "
                f"{round(growth * 100)}% year-over-year statewide "
                f"({prev} in {prev_year} to {last} in {last_year})", evidence)
            n_trends += 1

    # ---- anomalies ----------------------------------------------------------
    n_anom = 0
    for name, did, n in cur.execute(
            "SELECT cd.ComplainantName, u.DistrictID, COUNT(*) "
            "FROM ChargesheetDetails s "
            "JOIN ComplainantDetails cd ON cd.CaseMasterID=s.CaseMasterID "
            "JOIN CaseMaster c ON c.CaseMasterID=s.CaseMasterID "
            "JOIN Unit u ON u.UnitID=c.PoliceStationID "
            "WHERE s.cstype='B' GROUP BY 1, 2 HAVING COUNT(*) >= ? "
            "ORDER BY 3 DESC LIMIT 10", (ANOMALY_FALSE_CASES_MIN,)):
        evidence = [r[0] for r in cur.execute(
            "SELECT s.CaseMasterID FROM ChargesheetDetails s "
            "JOIN ComplainantDetails cd ON cd.CaseMasterID=s.CaseMasterID "
            "WHERE s.cstype='B' AND cd.ComplainantName=?", (name,))]
        add("anomaly", "district", did, None, None, AS_OF, n, 0, None,
            f"Serial false complainant: {n} complaints by '{name}' in "
            f"{names['district'].get(did, did)} closed as false cases",
            evidence)
        n_anom += 1

    for st, ifrom, brief_n in cur.execute(
            "SELECT PoliceStationID, IncidentFromDate, COUNT(*) FROM CaseMaster "
            "GROUP BY PoliceStationID, IncidentFromDate, BriefFacts "
            "HAVING COUNT(*) > 1 LIMIT 25"):
        evidence = [r[0] for r in cur.execute(
            "SELECT CaseMasterID FROM CaseMaster WHERE PoliceStationID=? AND "
            "IncidentFromDate=?", (st, ifrom))]
        add("anomaly", "station", st, None, None, AS_OF, brief_n, 1, None,
            f"Possible duplicate registration at {names['unit'].get(st, st)} "
            f"(same incident recorded {brief_n} times)", evidence)
        n_anom += 1

    durations = defaultdict(list)
    for st, days in cur.execute(
            "SELECT c.PoliceStationID, CAST(julianday(s.csdate) - "
            "julianday(c.CrimeRegisteredDate) AS INT) "
            "FROM ChargesheetDetails s "
            "JOIN CaseMaster c ON c.CaseMasterID=s.CaseMasterID "
            "WHERE s.cstype='A'"):
        durations[st].append(days)
    all_days = [d for lst in durations.values() for d in lst]
    state_median = statistics.median(all_days) if all_days else 0
    slow = sorted(((statistics.median(lst), st, len(lst))
                   for st, lst in durations.items()
                   if len(lst) >= SLOW_STATION_MIN_SHEETS
                   and statistics.median(lst) >= SLOW_STATION_RATIO * state_median),
                  reverse=True)[:15]
    for med, st, n in slow:
        add("anomaly", "station", st, None, None, AS_OF, med, state_median, None,
            f"Chronic delay: {names['unit'].get(st, st)} takes a median "
            f"{int(med)} days to chargesheet vs {int(state_median)} statewide",
            [])
        n_anom += 1

    cur.executemany("INSERT INTO x_alert VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return {"spikes": n_spikes, "emerging_trends": n_trends, "anomalies": n_anom}
