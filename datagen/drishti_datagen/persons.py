"""Offender identity pool — the ground-truth "people of the world".

Built in memory each run; the case engine (stage 1c) draws accused from this
pool, persists the ones actually used into x_person_master / x_person_alias,
and records the truth in x_er_gold. Criminological skew is deliberate:
~12% of offenders are repeaters carrying ~1/3 of all accused rows, some with
spelling variants and true street aliases — this is exactly what the entity
resolution engine must untangle later, with the gold labels to score it.
"""

import math

from .config import DISTRICT_HQ_COORDS
from .names import NICKNAMES
from .util import weighted

FEMALE_OFFENDER_RATE = 0.09        # NCRB-consistent order of magnitude
REPEAT_RATE = 0.12                 # 12% of offenders are repeat offenders
TRUE_ALIAS_RATE = 0.05             # of repeaters: carries a street alias
SPELLING_VARIANT_RATE = 0.35       # of repeaters: appears under variant spellings

# How many cases a repeater is budgeted for (long tail; avg ~3.5).
REPEAT_CASES = [(2, .40), (3, .25), (4, .15), (5, .08), (6, .05),
                (8, .04), (10, .02), (12, .01)]

AGE_BANDS = [((18, 24), .24), ((25, 30), .26), ((31, 36), .20),
             ((37, 44), .16), ((45, 55), .10), ((56, 68), .04)]

# Offence affinity: repeaters mostly specialize (drives MO consistency later).
SPECIALIZATIONS = [("property", .34), ("body", .22), ("cyber-fraud", .12),
                   ("ndps-excise", .12), ("women-related", .08), ("mixed", .12)]

BASE_YEAR = 2026


def _nearest_districts(names):
    """district -> 2 nearest other districts (for repeat-offender mobility)."""
    out = {}
    for a in names:
        la, lo = DISTRICT_HQ_COORDS[a]
        dist = sorted(((math.hypot(la - DISTRICT_HQ_COORDS[b][0],
                                   lo - DISTRICT_HQ_COORDS[b][1]), b)
                       for b in names if b != a))
        out[a] = [dist[0][1], dist[1][1]]
    return out


def build_offender_pool(ref, rngf, namef, count):
    rng = rngf.stream("persons")
    dnames = [d["name"] for d in ref["districts"]]
    dweights = [(d["name"], d["popEstimate"]) for d in ref["districts"]]
    neighbors = _nearest_districts(dnames)

    pool = []
    for pid in range(1, count + 1):
        home = weighted(rng, dweights)
        gender = "F" if rng.random() < FEMALE_OFFENDER_RATE else "M"
        p = namef.person(rng, home, gender=gender)
        (lo, hi) = weighted(rng, AGE_BANDS)
        age = rng.randint(lo, hi)
        repeat = rng.random() < REPEAT_RATE

        rec = {
            "pid": pid, "display": p["display"], "gender": gender,
            "religion": p["religion"], "birth_year": BASE_YEAR - age,
            "home": home, "repeat": repeat,
            "budget": weighted(rng, REPEAT_CASES) if repeat else 1,
            "spec": weighted(rng, SPECIALIZATIONS) if repeat else "mixed",
            "districts": [home], "variants": [], "alias": None, "used": 0,
            # World-truth identifiers. Real Aadhaar never starts with 0/1;
            # these are random synthetic values, masked wherever displayed.
            "aadhaar": f"{rng.randint(2, 9)}{rng.randint(0, 99999999999):011d}",
            "phone": f"{rng.choice('6789')}{rng.randint(0, 999999999):09d}",
        }
        if repeat:
            if rng.random() < 0.60:          # mobile repeaters cross district lines
                rec["districts"] += neighbors[home][:rng.randint(1, 2)]
            if rng.random() < SPELLING_VARIANT_RATE:
                rec["variants"].append(namef.variant_of(rec["display"], rng))
                if rng.random() < 0.35:
                    rec["variants"].append(namef.variant_of(rec["display"], rng))
            if rng.random() < TRUE_ALIAS_RATE:
                rec["alias"] = f"{rng.choice(NICKNAMES)} {p['first'].split()[0]}"
        pool.append(rec)

    stats = {
        "pool": len(pool),
        "repeaters": sum(1 for r in pool if r["repeat"]),
        "case_capacity": sum(r["budget"] for r in pool),
        "with_spelling_variants": sum(1 for r in pool if r["variants"]),
        "with_true_alias": sum(1 for r in pool if r["alias"]),
        "distinct_display_names": len({r["display"] for r in pool}),
        "cross_district": sum(1 for r in pool if len(r["districts"]) > 1),
    }
    return pool, stats
