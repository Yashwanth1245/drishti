"""The case engine: turns the crime-type catalog + offender pool into FIRs.

For each case it decides type -> year/date/time -> district/station -> incident
coordinates -> parties (complainant/victims/accused from the pool) -> legal
sections (IPC before the 2024-07-01 offence-date cutover, BNS after) ->
BriefFacts narrative (rendered from the SAME variables as the columns, so text
and data never contradict) -> identity captures, property, MO tags.

Persists only persons actually used into x_person_master / x_person_alias and
writes x_er_gold ground truth per named-accused row.
"""

import datetime as dt
import json

from .config import BNS_CUTOVER, SPAN_END, SPAN_START
from .crimetypes import (CRIME_TYPES, KANNADA_LINES, MOTIVES, TERSE, WEAPONS)
from .util import id_hash, weighted

YEAR_WEIGHTS = [(2021, .14), (2022, .155), (2023, .185),
                (2024, .195), (2025, .21), (2026, .115)]

# Identity-capture rates (see docs/DATA_MODEL.md). Arrest-time capture is 1d's.
CAPTURE_COMPLAINANT = 0.55
CAPTURE_VICTIM = 0.45
CAPTURE_NAMED_ACCUSED = 0.08
CAPTURE_TYPO = 0.02

VARIANT_USE_RATE = 0.30      # repeater appearances under a variant spelling
ALIAS_USE_RATE = 0.10
AGE_DRIFT_RATE = 0.30
KANNADA_RATE = 0.15
TERSE_RATE = 0.10

CHUNK = 20000

OCCUPATION_N = 25
CASTE_N = 22


def _hour(rng, hours):
    (lo, hi) = weighted(rng, hours)
    h = rng.randrange(lo, hi if hi > lo else hi + 24)
    return h % 24


def _mask(aadhaar):
    return "XXXX XXXX " + aadhaar[-4:]


def _typo(value, rng):
    i = rng.randrange(len(value) - 1)
    return value[:i] + value[i + 1] + value[i] + value[i + 2:]


class OffenderDraw:
    """Draws accused from the pool honoring budgets, districts, specialization."""

    SPEC_MAP = {"theft": "property", "vehicle_theft": "property", "burglary": "property",
                "robbery": "property", "snatching": "property", "dacoity": "property",
                "cheating": "property", "forgery": "property",
                "cyber_fraud": "cyber-fraud", "ndps": "ndps-excise",
                "excise": "ndps-excise", "gambling": "ndps-excise",
                "molestation": "women-related", "rape": "women-related",
                "cruelty_498a": "women-related", "dowry_death": "women-related",
                "murder": "body", "attempt_murder": "body", "hurt": "body",
                "kidnapping": "body", "rioting": "body"}
    ALL_SPECS = ["property", "body", "cyber-fraud", "ndps-excise",
                 "women-related", "mixed"]

    REPEATER_PICK_RATE = 0.45    # tuned so repeaters carry ~25-30% of accused rows
                                 # (0.28 yielded only 13% — budgets go unspent)

    def __init__(self, pool, rng, namef, ref):
        self.rng, self.namef, self.ref = rng, namef, ref
        self.pool = pool
        # O(1) draws: singles are popped once; repeaters live in per-spec stacks
        # and stay until their case budget is spent.
        self.singles = {}
        self.reps = {}
        for rec in pool:
            for d in rec["districts"]:
                if rec["repeat"]:
                    self.reps.setdefault(d, {}).setdefault(rec["spec"], []).append(rec)
                else:
                    self.singles.setdefault(d, []).append(rec)
        for lst in self.singles.values():
            rng.shuffle(lst)
        self.extra = 0

    def _draw_repeater(self, district, spec):
        # preferred spec first, then mixed, then any remaining (budgets must
        # not go unspent — the criminological skew depends on it)
        specs = [spec, "mixed"] + [s for s in self.ALL_SPECS
                                   if s not in (spec, "mixed")]
        dreps = self.reps.get(district, {})
        for s in specs:
            lst = dreps.get(s)
            while lst:
                rec = lst[-1]
                if rec["used"] >= rec["budget"]:
                    lst.pop()
                    continue
                rec["used"] += 1
                return rec
        return None

    def draw(self, district, ctype):
        spec = self.SPEC_MAP.get(ctype, "mixed")
        if self.rng.random() < self.REPEATER_PICK_RATE:
            rec = self._draw_repeater(district, spec)
            if rec:
                return rec
        lst = self.singles.get(district)
        while lst:
            rec = lst.pop()
            if rec["used"] == 0:          # may appear in two district lists
                rec["used"] = 1
                return rec
        rec = self._draw_repeater(district, spec)
        if rec:
            return rec
        # pool locally exhausted: mint a one-off person (keeps generation total)
        self.extra += 1
        p = self.namef.person(self.rng, district,
                              gender="F" if self.rng.random() < 0.09 else "M")
        rec = {"pid": len(self.pool) + 1, "display": p["display"], "gender": p["gender"],
               "religion": p["religion"], "birth_year": 2026 - self.rng.randint(19, 45),
               "home": district, "repeat": False, "budget": 1, "spec": "mixed",
               "districts": [district], "variants": [], "alias": None, "used": 1,
               "aadhaar": f"{self.rng.randint(2, 9)}{self.rng.randint(0, 99999999999):011d}",
               "phone": f"{self.rng.choice('6789')}{self.rng.randint(0, 999999999):09d}"}
        self.pool.append(rec)
        return rec


def _load_geo(conn):
    """stations per district with coords, buckets, IOs, courts, head/subhead ids."""
    cur = conn.cursor()
    did_name = dict(cur.execute("SELECT DistrictID, DistrictName FROM District"))
    stations = {}
    for uid, name, tid, did, lat, lon in cur.execute(
            "SELECT u.UnitID, u.UnitName, u.TypeID, u.DistrictID, g.latitude, g.longitude "
            "FROM Unit u JOIN x_unit_geo g ON g.UnitID=u.UnitID WHERE u.TypeID>=5"):
        d = stations.setdefault(did, {"regular": [], "rural": [], "women": [],
                                      "cen": [], "traffic": []})
        row = (uid, name, lat, lon)
        if tid == 6:
            d["women"].append(row)
        elif tid == 7:
            d["cen"].append(row)
        elif tid == 8 or "Traffic" in name:
            d["traffic"].append(row)
        elif "Rural" in name:
            d["rural"].append(row)
        else:
            d["regular"].append(row)
    ios = {}
    for uid, eid in cur.execute(
            "SELECT UnitID, EmployeeID FROM Employee WHERE RankID IN (8,9)"):
        ios.setdefault(uid, []).append(eid)
    courts = {}
    for cid, cname, did in cur.execute(
            "SELECT CourtID, CourtName, DistrictID FROM Court"):
        c = courts.setdefault(did, {"sessions": None, "jmfc": []})
        if "Sessions" in cname:
            c["sessions"] = cid
        else:
            c["jmfc"].append(cid)
    heads = dict(cur.execute("SELECT CrimeGroupName, CrimeHeadID FROM CrimeHead"))
    subheads = list(cur.execute(
        "SELECT CrimeSubHeadID, CrimeHeadID, CrimeHeadName FROM CrimeSubHead"))
    place_ids = {n: i for i, n in cur.execute(
        "SELECT PlaceTypeID, LookupValue FROM PlaceTypeMaster")}
    return did_name, stations, ios, courts, heads, subheads, place_ids


def _legal_for(ctype, spec, registry, use_bns):
    """(head_id_key, subhead_id_key, [(act, section), ...]) resolution data."""
    if spec["sll"]:
        return None, None, list(spec["sll"])
    kw = (spec["kw"] or "").lower()
    for off in registry:
        if kw and kw in off["short"].lower():
            sec = off["bns"] if use_bns else off["ipc"]
            act = "BNS" if use_bns else "IPC"
            if sec:
                return off["head_id"], off["subhead_id"], [(act, sec)]
    return None, None, [("BNS" if use_bns else "IPC", "34")]


def build_cases(conn, ref, rngf, seq, namef, pool, registry, n_cases):
    rng = rngf.stream("cases")
    did_name, stations, ios, courts, heads, subheads, place_ids = _load_geo(conn)
    name_did = {v: k for k, v in did_name.items()}
    draw = OffenderDraw(pool, rng, namef, ref)

    dweights = [(d["name"], d["popEstimate"]) for d in ref["districts"]]
    types = list(CRIME_TYPES.items())
    type_weights = [(k, v["weight"]) for k, v in types]
    misc_head = heads.get("Miscellaneous IPC/BNS Crimes", list(heads.values())[-1])
    sll_head = heads.get("Special & Local Laws (SLL)", misc_head)
    sub_by_head = {}
    for sid, hid, _ in subheads:
        sub_by_head.setdefault(hid, sid)

    span_start = dt.date.fromisoformat(SPAN_START)
    span_end = dt.date.fromisoformat(SPAN_END)
    cutover = dt.date.fromisoformat(BNS_CUTOVER)

    rows = {k: [] for k in ("case", "compl", "victim", "accused", "asa", "occ",
                            "idcap", "prop", "mo")}
    serials = {}
    person_seen = {}     # pid -> {"first": date, "last": date, "rec": rec}
    gold, roles = [], []
    proc = []            # per-case handoff to the process engine (stage 1d)
    stats = {"cases": 0, "accused_rows": 0, "victim_rows": 0, "unknown_cases": 0}

    def flush():
        cur = conn.cursor()
        cur.executemany("INSERT INTO CaseMaster VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows["case"])
        cur.executemany("INSERT INTO ComplainantDetails VALUES (?,?,?,?,?,?,?,?)", rows["compl"])
        cur.executemany("INSERT INTO Victim VALUES (?,?,?,?,?,?)", rows["victim"])
        cur.executemany("INSERT INTO Accused VALUES (?,?,?,?,?,?)", rows["accused"])
        cur.executemany("INSERT INTO ActSectionAssociation VALUES (?,?,?,?,?)", rows["asa"])
        cur.executemany("INSERT INTO Inv_OccuranceTime VALUES (?,?,?,?)", rows["occ"])
        cur.executemany("INSERT INTO x_identity_capture VALUES (?,?,?,?,?,?,?)", rows["idcap"])
        cur.executemany("INSERT INTO x_property VALUES (?,?,?,?,?,?,?)", rows["prop"])
        cur.executemany("INSERT INTO x_mo_tag VALUES (?,?,?,?)", rows["mo"])
        conn.commit()
        for k in rows:
            rows[k].clear()

    for _ in range(n_cases):
        ctype = weighted(rng, type_weights)
        spec = CRIME_TYPES[ctype]

        # -- when ----------------------------------------------------------
        yw = YEAR_WEIGHTS
        if spec["year_mult"]:
            yw = [(y, w * spec["year_mult"].get(y, 1.0)) for y, w in YEAR_WEIGHTS]
        year = weighted(rng, yw)
        month_w = [(m, (1.0 if not (year == 2026 and m > 6) else 0.0) *
                    spec["months"].get(m, 1.0)) for m in range(1, 13)]
        month = weighted(rng, month_w)
        day = rng.randint(1, 28)
        hour = _hour(rng, spec["hours"])
        incident = dt.datetime(year, month, day, hour, rng.randrange(60))
        idate = incident.date()
        if idate < span_start or idate > span_end:
            idate = min(max(idate, span_start), span_end)
            incident = dt.datetime.combine(idate, incident.time())
        delay = weighted(rng, spec["delay"])
        reg_date = min(idate + dt.timedelta(days=delay + rng.randint(0, 1)), span_end)

        # -- where ----------------------------------------------------------
        if spec["bshare"] is not None and rng.random() < spec["bshare"]:
            dname = "Bengaluru Urban"
        else:
            dname = weighted(rng, dweights)
        did = name_did[dname]
        b = stations[did]
        pref = spec["station"]
        bucket = None
        if pref == "cen" and b["cen"] and rng.random() < .7:
            bucket = b["cen"]
        elif pref == "women" and b["women"] and rng.random() < .4:
            bucket = b["women"]
        elif pref == "traffic" and b["traffic"] and rng.random() < .55:
            bucket = b["traffic"]
        if bucket is None:
            bucket = b["regular"] if (b["regular"] and (not b["rural"] or rng.random() < .69)) \
                else (b["rural"] or b["regular"])
        st_uid, st_name, st_lat, st_lon = rng.choice(bucket)
        lat = st_lat + rng.uniform(-0.02, 0.02)
        lon = st_lon + rng.uniform(-0.02, 0.02)
        place_name = st_name.replace(" PS", "")
        place_type = weighted(rng, spec["places"])

        # -- case identity ---------------------------------------------------
        if ctype == "udr":
            cat = 3
        elif ctype in ("gambling", "excise") and rng.random() < .25:
            cat = 4
        elif rng.random() < .015:
            cat = 8       # Zero FIR
        else:
            cat = 1
        skey = (st_uid, cat, reg_date.year)
        serials[skey] = serials.get(skey, 0) + 1
        crime_no = f"{cat}{did:04d}{st_uid:04d}{reg_date.year}{serials[skey]:05d}"
        case_id = seq.next("case")

        # -- parties ----------------------------------------------------------
        comp_gender = "F" if (spec["female_victim"] and spec["victim"] == "self") else None
        comp = namef.person(rng, dname, gender=comp_gender)
        comp_id = seq.next("compl")
        comp_age = rng.randint(21, 65)

        victims = []
        if spec["victim"] != "state":
            if spec["victim"] == "self":
                vname, vgender = comp["display"], comp["gender"]
                vage = comp_age
            else:
                vg = "F" if spec["female_victim"] else ("M" if rng.random() < .65 else "F")
                vp = namef.person(rng, dname, gender=vg)
                vname, vgender, vage = vp["display"], vg, rng.randint(16, 70)
            victims.append((seq.next("victim"), vname, vage, vgender))

        unknown = rng.random() < spec["unknown"]
        accused = []
        if not unknown:
            case_pids = set()
            for i in range(weighted(rng, spec["n_accused"])):
                rec = draw.draw(dname, ctype)
                if rec["pid"] in case_pids:      # same person can't be A1 and A2
                    continue
                case_pids.add(rec["pid"])
                shown = rec["display"]
                if rec["variants"] and rng.random() < VARIANT_USE_RATE:
                    shown = rng.choice(rec["variants"])
                elif rec["alias"] and rng.random() < ALIAS_USE_RATE:
                    shown = rec["alias"]
                age = 2026 - rec["birth_year"]
                if rng.random() < AGE_DRIFT_RATE:
                    age += rng.choice((-2, -1, 1, 2))
                aid = seq.next("accused")
                accused.append((aid, rec, shown, max(age, 18)))
                ps = person_seen.setdefault(rec["pid"], {"first": idate, "last": idate,
                                                         "rec": rec})
                ps["first"] = min(ps["first"], idate)
                ps["last"] = max(ps["last"], idate)
        else:
            stats["unknown_cases"] += 1

        # -- legal -------------------------------------------------------------
        use_bns = idate >= cutover
        head_id, subhead_id, sections = _legal_for(ctype, spec, registry, use_bns)
        if head_id is None:
            head_id = sll_head if spec["sll"] else misc_head
            subhead_id = sub_by_head.get(head_id)
        if len(accused) > 1 and not spec["sll"] and rng.random() < .6:
            sections.append(("BNS", "3(5)") if use_bns else ("IPC", "34"))

        # -- property -----------------------------------------------------------
        prop_desc, prop_value = None, None
        if spec["prop"]:
            kind, recov_rate = spec["prop"]
            if kind == "vehicle" or (kind == "mixed" and rng.random() < .3):
                reg = (f"KA-{rng.randint(1, 65):02d}-"
                       f"{chr(rng.randint(65, 90))}{chr(rng.randint(65, 90))}-"
                       f"{rng.randint(1000, 9999)}")
                prop_desc = rng.choice(["Hero Splendor motorcycle", "Honda Activa scooter",
                                        "TVS XL moped", "Bajaj Pulsar motorcycle",
                                        "Maruti Swift car"]) + f" bearing reg no {reg}"
                prop_value = rng.choice([35000, 48000, 55000, 70000, 420000])
                identifier, pkind = reg, "vehicle"
            elif kind == "gold" or (kind == "mixed" and rng.random() < .4):
                grams = rng.choice([10, 15, 20, 25, 40])
                prop_desc = f"gold chain of {grams} grams"
                prop_value = grams * 6200
                identifier, pkind = None, "gold-jewellery"
            elif kind == "cash":
                prop_value = rng.choice([15000, 40000, 85000, 150000, 380000, 900000])
                prop_desc = f"cash of Rs. {prop_value}"
                identifier, pkind = None, "cash"
            else:
                prop_value = rng.choice([12000, 18000, 25000])
                prop_desc = "a mobile phone"
                identifier = f"IMEI-{rng.randint(10**14, 10**15 - 1)}"
                pkind = "mobile"
            rows["prop"].append((seq.next("prop"), case_id, pkind, prop_desc,
                                 identifier, prop_value,
                                 1 if rng.random() < recov_rate else 0))

        # -- narrative -----------------------------------------------------------
        mo_pool = spec["mo"]
        if ctype == "snatching":     # tag must agree with the incident hour
            mo_pool = [t for t in mo_pool if t != "morning-walk-target"] \
                if hour >= 12 else mo_pool
        mo_tags = rng.sample(mo_pool, k=min(len(mo_pool), rng.choice((1, 1, 2)))) \
            if mo_pool else []
        for t in mo_tags:
            rows["mo"].append((case_id, t, "rule", 1.0))
        acc_text = ", ".join(a[2] for a in accused) if accused else \
            ("unknown persons" if unknown else "the accused")
        if rng.random() < TERSE_RATE:
            brief = f"{rng.choice(TERSE)} Sections applied: " + \
                ", ".join(f"{a} {s}" for a, s in sections) + "."
        else:
            ctx = {"comp": comp["display"], "vict": victims[0][1] if victims else "the victim",
                   "acc": acc_text, "date": idate.isoformat(),
                   "time": f"{incident.hour:02d}{incident.minute:02d}",
                   "time2": f"{(incident.hour + rng.randint(1, 5)) % 24:02d}00",
                   "place": f"{place_name}, {dname}",
                   "prop": prop_desc or "valuables", "value": prop_value or 0,
                   "weapon": rng.choice(WEAPONS), "motive": rng.choice(MOTIVES),
                   "mo_phrase": (mo_tags[0].replace("-", " ") if mo_tags else "deceit"),
                   "mo_s": "MO: " + ", ".join(mo_tags) + "." if mo_tags else "",
                   "crel": rng.choice(["father", "brother", "wife", "son"]),
                   "nacc": len(accused) or 5,
                   "qty": rng.choice(["2 kg of ganja", "45 grams of MDMA",
                                      "18 grams of charas"])}
            brief = rng.choice(spec["templates"]).format(**ctx) if spec["templates"] \
                else f"Case of {ctype} registered at {place_name}. {ctx['mo_s']}"
            if rng.random() < KANNADA_RATE:
                brief += " " + rng.choice(KANNADA_LINES)

        # -- rows ------------------------------------------------------------------
        court = courts[did]
        court_id = court["sessions"] if spec["gravity"] == 1 else \
            (rng.choice(court["jmfc"]) if court["jmfc"] else court["sessions"])
        io_id = rng.choice(ios.get(st_uid) or [None])
        reg_dt_s = reg_date.isoformat()
        rows["case"].append((case_id, crime_no, f"{reg_date.year}{serials[skey]:05d}",
                             reg_dt_s, io_id, st_uid, cat, spec["gravity"], head_id,
                             subhead_id, 1, court_id, incident.isoformat(sep=" "),
                             (incident + dt.timedelta(hours=rng.randint(0, 4)))
                             .isoformat(sep=" "),
                             f"{reg_dt_s} {rng.randint(8, 20):02d}:{rng.randrange(60):02d}",
                             round(lat, 5), round(lon, 5), brief))
        rows["compl"].append((comp_id, case_id, comp["display"], comp_age,
                              rng.randint(1, OCCUPATION_N),
                              {"Hindu": 1, "Muslim": 2, "Christian": 3}.get(comp["religion"], 7),
                              rng.randint(1, CASTE_N),
                              1 if comp["gender"] == "M" else 2))
        for vid, vname, vage, vgender in victims:
            rows["victim"].append((vid, case_id, vname, vage, vgender,
                                   "1" if rng.random() < .01 else "0"))
            stats["victim_rows"] += 1
        for order, (aid, rec, shown, age) in enumerate(accused, 1):
            rows["accused"].append((aid, case_id, shown, age, rec["gender"],
                                    f"A{order}"))
            gold.append(("Accused", aid, rec["pid"]))
            roles.append((rec["pid"], case_id, "accused", aid, 1.0, "generator"))
            stats["accused_rows"] += 1
            if rng.random() < CAPTURE_NAMED_ACCUSED:
                rows["idcap"].append((case_id, "accused", aid, "aadhaar",
                                      rec["aadhaar"],
                                      id_hash(rec["aadhaar"]), reg_dt_s))
        for act_o, (act, sec) in enumerate(sections, 1):
            rows["asa"].append((case_id, act, sec, act_o, act_o))
        rows["occ"].append((case_id, f"{(hour // 3) * 3:02d}-{(hour // 3) * 3 + 3:02d}",
                            place_ids.get(place_type, 2), place_name))

        # identity captures for cooperative parties
        if rng.random() < CAPTURE_COMPLAINANT:
            full = f"{rng.randint(2, 9)}{rng.randint(0, 99999999999):011d}"
            if rng.random() < CAPTURE_TYPO:
                full = _typo(full, rng)      # hash reflects what was ENTERED
            rows["idcap"].append((case_id, "complainant", comp_id, "aadhaar",
                                  full, id_hash(full), reg_dt_s))
        if victims and spec["victim"] != "self" and rng.random() < CAPTURE_VICTIM:
            phone = f"{rng.choice('6789')}{rng.randint(0, 999999999):09d}"
            rows["idcap"].append((case_id, "victim", victims[0][0], "phone",
                                  phone, None, reg_dt_s))

        proc.append((case_id, ctype, reg_dt_s, st_uid, did, io_id, court_id,
                     unknown, [(aid, rec["pid"], rec["aadhaar"], rec["phone"])
                               for aid, rec, _, _ in accused]))
        stats["cases"] += 1
        if len(rows["case"]) >= CHUNK:
            flush()
    flush()

    # -- persist used persons + truth ---------------------------------------------
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO x_person_master VALUES (?,?,?,?,?,?,?,?,NULL,?,?)",
        [(pid, ps["rec"]["display"], ps["rec"]["gender"], ps["rec"]["birth_year"],
          name_did[ps["rec"]["home"]], ps["rec"]["religion"], ps["rec"]["aadhaar"],
          ps["rec"]["phone"], ps["first"].isoformat(), ps["last"].isoformat())
         for pid, ps in person_seen.items()])
    alias_rows = []
    for pid, ps in person_seen.items():
        for v in ps["rec"]["variants"]:
            alias_rows.append((pid, v, "spelling-variant"))
        if ps["rec"]["alias"]:
            alias_rows.append((pid, ps["rec"]["alias"], "true-alias"))
    cur.executemany("INSERT INTO x_person_alias VALUES (?,?,?)", alias_rows)
    cur.executemany("INSERT INTO x_er_gold VALUES (?,?,?)", gold)
    cur.executemany("INSERT INTO x_person_case_role VALUES (?,?,?,?,?,?)", roles)
    for act, sec in {(a, s) for (_, a, s, _, _) in
                     conn.execute("SELECT * FROM ActSectionAssociation")}:
        cur.execute("INSERT OR IGNORE INTO Section VALUES (?,?,?,1)", (act, sec, ""))
    conn.commit()

    stats["persons_used"] = len(person_seen)
    stats["aliases"] = len(alias_rows)
    stats["minted_extra_persons"] = draw.extra
    return stats, proc
