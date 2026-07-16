"""The process engine: what happens to a case AFTER registration.

Arrests/surrenders (with the time-ramped Aadhaar capture that gives entity
resolution its high-confidence anchors), chargesheets with the cstype outcome
mix calibrated per crime type (NCRB: overall ~77%, but theft ~30%, cyber ~18%,
murder ~89%), final case statuses, and a handful of deliberately slow stations
(a management insight the dashboards can surface). Cases too recent to have
concluded remain Under Investigation — time is respected everywhere.
"""

import datetime as dt

from .config import SPAN_END
from .util import id_hash, weighted

# ctype -> (chargesheet rate among concluded, false-case rate, arrest rate).
# Sources: reference/crime_calibration.json chargesheetRates; gaps filled with
# the all-India crime-head rates noted there.
OUTCOMES = {
    "murder": (.89, .01, .92), "attempt_murder": (.85, .01, .85),
    "hurt": (.80, .03, .75), "kidnapping": (.07, .05, .30),
    "rape": (.85, .04, .90), "molestation": (.80, .05, .70),
    "cruelty_498a": (.75, .08, .50), "dowry_death": (.90, .02, .95),
    "rioting": (.82, .02, .80),
    "theft": (.30, .03, .85), "vehicle_theft": (.25, .02, .85),
    "snatching": (.45, .01, .85), "robbery": (.73, .01, .85),
    "dacoity": (.78, .01, .90), "burglary": (.44, .02, .85),
    "cheating": (.55, .06, .60), "forgery": (.50, .05, .55),
    "cyber_fraud": (.18, .01, .50),
    "mischief": (.60, .04, .70), "trespass": (.65, .05, .70),
    "intimidation": (.60, .06, .60),
    "road_304a": (.85, .01, .80), "rash_driving": (.90, .005, .95),
    "ndps": (.95, .005, 1.0), "gambling": (.97, .005, 1.0),
    "excise": (.97, .005, 1.0),
}
DEFAULT_OUTCOME = (.60, .03, .70)

RED_HANDED = {"ndps", "gambling", "excise"}          # arrested during the raid
UNKNOWN_FINAL_C_RATE = 0.55       # unknown-accused cases closed as undetected
SURRENDER_RATE = 0.10
SLOW_STATION_RATE = 0.05
SLOW_FACTOR = 1.6
TRANSFER_RATE = 0.015
DISPOSED_RATE = 0.45              # old chargesheeted cases decided by court

INVESTIGATION_DAYS = [(45, .20), (70, .30), (90, .20), (150, .15),
                      (270, .10), (420, .05)]
ARREST_DELAY_DAYS = [(1, .30), (5, .25), (15, .20), (45, .15), (120, .10)]

# Arrest-time Aadhaar capture ramps with digitization (docs/DATA_MODEL.md).
def _aadhaar_rate(year):
    return min(0.65, 0.35 + 0.06 * (year - 2021))


STATUS_UI, STATUS_CS, STATUS_FALSE, STATUS_UNDET, STATUS_DISPOSED, STATUS_TRANSFER = \
    1, 2, 3, 4, 5, 6


def build_process(conn, rngf, seq, proc):
    rng = rngf.stream("process")
    span_end = dt.date.fromisoformat(SPAN_END)

    stations = sorted({p[3] for p in proc})
    slow = set(rng.sample(stations, int(len(stations) * SLOW_STATION_RATE)))

    arrests, junction, sheets, statuses, idcap = [], [], [], [], []
    stats = {"arrests": 0, "surrenders": 0, "chargesheets": 0, "false_cases": 0,
             "undetected": 0, "disposed": 0, "arrest_aadhaar_captures": 0}

    for (case_id, ctype, reg_iso, st_uid, did, io_id, court_id,
         unknown, accused) in proc:
        reg = dt.date.fromisoformat(reg_iso)
        cs_rate, false_rate, arrest_rate = OUTCOMES.get(ctype, DEFAULT_OUTCOME)
        dur = weighted(rng, INVESTIGATION_DAYS)
        if st_uid in slow:
            dur = int(dur * SLOW_FACTOR)
        cs_date = reg + dt.timedelta(days=dur)
        concluded = cs_date <= span_end

        # ---- arrests (named accused only) --------------------------------
        for (aid, pid, aadhaar, phone) in accused:
            if rng.random() >= arrest_rate:
                continue
            delay = 0 if ctype in RED_HANDED else weighted(rng, ARREST_DELAY_DAYS)
            adate = reg + dt.timedelta(days=delay)
            if adate > span_end:
                continue
            surrender = rng.random() < SURRENDER_RATE and ctype not in RED_HANDED
            r = rng.random()
            if r < .015:                       # fled across the state border
                a_state, a_did = 1 + rng.randint(1, 6), None
            elif r < .095:                     # picked up in another district
                a_state, a_did = 1, 1000 + rng.randint(1, 31)
            else:
                a_state, a_did = 1, did
            as_id = seq.next("arrest")
            arrests.append((as_id, case_id, 2 if surrender else 1,
                            adate.isoformat(), a_state, a_did, st_uid, io_id,
                            court_id, aid, 1, 0))
            junction.append((as_id, aid))
            stats["surrenders" if surrender else "arrests"] += 1
            if rng.random() < _aadhaar_rate(adate.year):
                idcap.append((case_id, "accused", aid, "aadhaar",
                              aadhaar, id_hash(aadhaar),
                              adate.isoformat()))
                stats["arrest_aadhaar_captures"] += 1
            if rng.random() < 0.25:
                idcap.append((case_id, "accused", aid, "phone", phone, None,
                              adate.isoformat()))

        # ---- outcome -------------------------------------------------------
        if ctype == "udr":
            if concluded and rng.random() < .75:
                sheets.append((seq.next("cs"), case_id, cs_date.isoformat(),
                               "C", io_id))
                statuses.append((STATUS_UNDET, case_id))
                stats["undetected"] += 1
            continue
        if rng.random() < TRANSFER_RATE:
            statuses.append((STATUS_TRANSFER, case_id))
            continue
        if not concluded:
            continue                            # stays Under Investigation
        if unknown:
            if rng.random() < UNKNOWN_FINAL_C_RATE:
                sheets.append((seq.next("cs"), case_id, cs_date.isoformat(),
                               "C", io_id))
                statuses.append((STATUS_UNDET, case_id))
                stats["undetected"] += 1
            continue
        r = rng.random()
        if r < cs_rate:
            sheets.append((seq.next("cs"), case_id, cs_date.isoformat(), "A", io_id))
            stats["chargesheets"] += 1
            old = cs_date + dt.timedelta(days=400) <= span_end
            if old and rng.random() < DISPOSED_RATE:
                statuses.append((STATUS_DISPOSED, case_id))
                stats["disposed"] += 1
            else:
                statuses.append((STATUS_CS, case_id))
        elif r < cs_rate + false_rate:
            sheets.append((seq.next("cs"), case_id, cs_date.isoformat(), "B", io_id))
            statuses.append((STATUS_FALSE, case_id))
            stats["false_cases"] += 1
        # remainder: named accused but evidence insufficient — stays open

    cur = conn.cursor()
    cur.executemany("INSERT INTO ArrestSurrender VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    arrests)
    cur.executemany("INSERT INTO inv_arrestsurrenderaccused VALUES (?,?)", junction)
    cur.executemany("INSERT INTO ChargesheetDetails VALUES (?,?,?,?,?)", sheets)
    cur.executemany("INSERT INTO x_identity_capture VALUES (?,?,?,?,?,?,?)", idcap)
    cur.executemany("UPDATE CaseMaster SET CaseStatusID=? WHERE CaseMasterID=?",
                    statuses)
    conn.commit()

    stats["slow_stations"] = len(slow)
    return stats
