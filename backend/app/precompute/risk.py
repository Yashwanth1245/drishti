"""Entity risk scoring — an explainable composite, never a black box.

risk = frequency + recency + gravity + escalation + breadth (weights in
config.RISK_W, total 100). Every component lands in risk_factors JSON so the
profile page can show exactly WHY someone scores 91 — a judged requirement
(explainable AI) and the difference between decision support and profiling.
"""

import datetime as dt
import json
from collections import defaultdict

from ..config import AS_OF, RISK_FREQ_SATURATION, RISK_RECENCY_HORIZON, RISK_W


def build(conn):
    cur = conn.cursor()
    as_of = dt.date.fromisoformat(AS_OF)

    ent_cases = defaultdict(list)
    for eid, cid, date, gravity, did in cur.execute(
            "SELECT m.entity_id, m.CaseMasterID, c.CrimeRegisteredDate, "
            "c.GravityOffenceID, u.DistrictID "
            "FROM x_entity_member m "
            "JOIN CaseMaster c ON c.CaseMasterID=m.CaseMasterID "
            "JOIN Unit u ON u.UnitID=c.PoliceStationID "
            "GROUP BY m.entity_id, m.CaseMasterID"):
        ent_cases[eid].append((date, gravity, did))

    updates = []
    for eid, cases in ent_cases.items():
        cases.sort()
        n = len(cases)
        frequency = min(1.0, (n - 1) / RISK_FREQ_SATURATION)
        days_since = (as_of - dt.date.fromisoformat(cases[-1][0])).days
        recency = max(0.0, 1 - days_since / RISK_RECENCY_HORIZON)
        heinous = [g == 1 for _, g, _ in cases]
        gravity = 0.6 * (sum(heinous) / n) + (0.4 if any(heinous) else 0.0)
        if n >= 2 and heinous[-1] and not heinous[0]:
            escalation = 1.0            # started non-heinous, now heinous
        elif all(heinous):
            escalation = 0.3
        else:
            escalation = 0.0
        breadth = min(1.0, (len({d for _, _, d in cases}) - 1) / 2)

        parts = {"frequency": frequency, "recency": recency, "gravity": gravity,
                 "escalation": escalation, "breadth": breadth}
        score = round(sum(RISK_W[k] * v for k, v in parts.items()), 1)
        factors = {k: {"score": round(v, 2), "weight": RISK_W[k]}
                   for k, v in parts.items()}
        factors["inputs"] = {"cases": n, "days_since_last": days_since,
                             "heinous_cases": sum(heinous),
                             "districts": len({d for _, _, d in cases})}
        updates.append((score, json.dumps(factors), eid))

    cur.executemany(
        "UPDATE x_entity SET risk_score=?, risk_factors=? WHERE entity_id=?",
        updates)
    conn.commit()
    top = cur.execute("SELECT MAX(risk_score) FROM x_entity").fetchone()[0]
    return {"entities_scored": len(updates), "max_risk": top}
