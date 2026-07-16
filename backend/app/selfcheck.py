"""Engine self-check: assert the intelligence layer finds the planted truth.

Unlike datagen's --verify (which checks the DATA), this checks the ENGINES:
entity resolution must have resolved the stories, the spike detector must have
fired for Hubballi, risk must rank the planted offenders high, anomalies must
surface the serial false complainant. Run from backend/:

    ../.venv/bin/python -m app.selfcheck
"""

import json
import sys

from .config import ROOT
from .db import connect


def main():
    conn = connect(readonly=True)
    q = lambda sql, *p: conn.execute(sql, p).fetchone()
    stories = json.loads((ROOT / "exports" / "stories.json").read_text())
    failures = []

    def check(label, ok, detail=""):
        print(f"  {'PASS' if ok else 'FAIL'}  {label}" +
              (f": {detail}" if detail != "" else ""))
        if not ok:
            failures.append(label)

    # ---- ER quality -------------------------------------------------------
    metrics = {k: json.loads(v) for k, v in
               conn.execute("SELECT key, value FROM x_metric")}
    check("ER precision >= 0.90", metrics["er_precision"] >= 0.90,
          metrics["er_precision"])
    check("ER recall >= 0.25", metrics["er_recall"] >= 0.25,
          metrics["er_recall"])
    check("no blob entities (largest < 30 rows)",
          q("SELECT MAX(n_rows) FROM x_entity")[0] < 30,
          q("SELECT MAX(n_rows) FROM x_entity")[0])

    def entity_of(pid):
        row = q("SELECT m.entity_id, COUNT(*) FROM x_er_gold g "
                "JOIN x_entity_member m ON m.AccusedMasterID=g.source_row_id "
                "WHERE g.true_person_id=? GROUP BY 1 ORDER BY 2 DESC", pid)
        return row

    # ---- S1: the serial snatcher ------------------------------------------
    s1 = entity_of(stories["S1_serial_snatcher"]["person_id"])
    check("S1 resolved into ONE entity with 11 cases",
          s1 is not None and s1[1] == 11, s1)
    if s1:
        risk, = q("SELECT risk_score FROM x_entity WHERE entity_id=?", s1[0])
        rank, = q("SELECT COUNT(*) FROM x_entity WHERE risk_score > ?", risk)
        check("S1 risk in statewide top 50 (of ~216k entities)", rank < 50,
              f"risk {risk}, rank {rank + 1}")
        n_dist, = q("SELECT COUNT(DISTINCT u.DistrictID) FROM x_entity_member m "
                    "JOIN CaseMaster c ON c.CaseMasterID=m.CaseMasterID "
                    "JOIN Unit u ON u.UnitID=c.PoliceStationID "
                    "WHERE m.entity_id=?", s1[0])
        check("S1 entity spans 3 districts", n_dist == 3, n_dist)

    # ---- S1 spike: Dharwad robbery/snatching surge --------------------------
    spike = q("SELECT summary FROM x_alert WHERE kind='spike' AND "
              "scope_type='district' AND scope_id="
              "(SELECT DistrictID FROM District WHERE DistrictName='Dharwad') "
              "AND (summary LIKE '%natch%' OR summary LIKE '%Snatch%')")
    check("spike alert fired for Dharwad snatching surge", spike is not None,
          spike[0] if spike else "none")

    # ---- S4: escalation ------------------------------------------------------
    s4 = entity_of(stories["S4_escalating_offender"]["person_id"])
    check("S4 resolved into ONE entity with 4 cases",
          s4 is not None and s4[1] == 4, s4)
    if s4:
        factors = json.loads(q("SELECT risk_factors FROM x_entity WHERE "
                               "entity_id=?", s4[0])[0])
        check("S4 escalation factor detected",
              factors["escalation"]["score"] == 1.0, factors["escalation"])

    # ---- S2: the ring --------------------------------------------------------
    fence = entity_of(stories["S2_vehicle_ring"]["fence_pid"])
    check("S2 fence resolved into ONE entity with 4 cases",
          fence is not None and fence[1] == 4, fence)
    if fence:
        deg, = q("SELECT COUNT(*) FROM x_network_edge WHERE "
                 "(src_id=? OR dst_id=?) AND edge_type='co-accused'",
                 fence[0], fence[0])
        check("S2 fence has network degree >= 4", deg >= 4, deg)

    # ---- S5 + trends + rollups ----------------------------------------------
    check("serial-false-complainant anomaly (Gangamma)",
          q("SELECT 1 FROM x_alert WHERE kind='anomaly' AND summary LIKE "
            "'%Gangamma%'") is not None)
    check("emerging-trend alert exists (cyber growth)",
          q("SELECT 1 FROM x_alert WHERE kind='emerging-trend'") is not None)
    agg, cases = (q("SELECT SUM(n) FROM x_agg_daily")[0],
                  q("SELECT COUNT(*) FROM CaseMaster")[0])
    check("rollup totals match CaseMaster", agg == cases, f"{agg} vs {cases}")

    print("SELFCHECK:", "ALL PASS" if not failures else f"FAILURES: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
