"""Planted crime stories — the demo's scripted reveals (S1-S5).

Injected AFTER bulk generation so they ride on realistic background noise.
Each story writes complete case lifecycles (cases, parties, sections, arrests,
chargesheets, statuses, identity captures, MO tags, property) and registers
itself in the manifest returned to the pipeline (persisted as
exports/stories.json — the demo answer key and the validator's assertion list).

S1 serial chain-snatcher across 3 districts, 2 spellings + alias, live spike
S2 vehicle-theft ring: 6 thieves in rotating pairs + one fence linking all
S3 investment-app cyber fraud: statewide victims, 5 mule accounts (finance 1f)
S4 domestic-violence offender escalating 498A -> hurt -> attempt murder
S5 serial false complainant: 6 cases, all closed as false
"""

import datetime as dt
import json

from .cases import _legal_for, _load_geo
from .util import id_hash
from .config import EXPORT_DIR

GOLD_RATE_PER_GRAM = 6200


class StoryWriter:
    """Row-level plumbing shared by all stories."""

    def __init__(self, conn, seq, registry):
        self.conn, self.seq, self.registry = conn, seq, registry
        (self.did_name, self.stations, self.ios, self.courts,
         self.heads, self.subheads, self.place_ids) = _load_geo(conn)
        self.name_did = {v: k for k, v in self.did_name.items()}
        self.pid_next = conn.execute(
            "SELECT COALESCE(MAX(person_id),0)+1 FROM x_person_master").fetchone()[0]
        self.case_ids = []

    def person(self, name, gender, birth_year, home, aadhaar, phone,
               variants=(), alias=None):
        pid = self.pid_next
        self.pid_next += 1
        cur = self.conn.cursor()
        cur.execute("INSERT INTO x_person_master VALUES (?,?,?,?,?,?,?,?,NULL,?,?)",
                    (pid, name, gender, birth_year, self.name_did[home], "Hindu",
                     aadhaar, phone, "2021-01-01", "2026-06-30"))
        for v in variants:
            cur.execute("INSERT INTO x_person_alias VALUES (?,?,?)",
                        (pid, v, "spelling-variant"))
        if alias:
            cur.execute("INSERT INTO x_person_alias VALUES (?,?,?)",
                        (pid, alias, "true-alias"))
        return {"pid": pid, "name": name, "gender": gender,
                "birth_year": birth_year, "aadhaar": aadhaar, "phone": phone}

    def station(self, district, contains=None, kind="regular"):
        b = self.stations[self.name_did[district]]
        pool = b[kind] or b["regular"] or b["rural"]
        if contains:
            hits = [s for s in pool if contains.lower() in s[1].lower()]
            pool = hits or pool
        return pool[0]

    def _serial(self, st_uid, cat, year):
        # MAX+1, not COUNT+1: counts drift from serials once several stages
        # insert at the same station/category/year (CrimeNo layout: pos 10-13
        # is the year, last 5 digits the serial). Inserts here are immediate,
        # so repeated calls see prior story rows.
        top = self.conn.execute(
            "SELECT MAX(CAST(substr(CrimeNo,-5) AS INTEGER)) FROM CaseMaster "
            "WHERE PoliceStationID=? AND CaseCategoryID=? AND substr(CrimeNo,10,4)=?",
            (st_uid, cat, str(year))).fetchone()[0]
        return (top or 0) + 1

    def case(self, ctype, district, station, incident, brief, accused=(),
             shown_names=None, complainant=("Complainant", 45, "M"),
             victim=None, mo=(), prop=None, arrest=None, outcome=None,
             delay_days=0, value=None):
        """Writes one complete case; returns CaseMasterID.

        accused: list of person dicts. arrest: {idx, date, aadhaar_capture}.
        outcome: None (open) | ('A'|'B'|'C', csdate).
        """
        from .crimetypes import CRIME_TYPES
        spec = CRIME_TYPES[ctype]
        cur = self.conn.cursor()
        st_uid, st_name, st_lat, st_lon = station
        did = self.name_did[district]
        reg = min(incident.date() + dt.timedelta(days=delay_days),
                  dt.date(2026, 6, 30))
        cat = 1
        serial = self._serial(st_uid, cat, reg.year)
        crime_no = f"{cat}{did:04d}{st_uid:04d}{reg.year}{serial:05d}"
        case_id = self.seq.next("case")
        self.case_ids.append(case_id)

        use_bns = incident.date() >= dt.date(2024, 7, 1)
        head_id, subhead_id, sections = _legal_for(ctype, spec, self.registry, use_bns)
        if head_id is None:
            head_id = self.heads.get("Special & Local Laws (SLL)")
            subhead_id = None
        if len(accused) > 1 and not spec["sll"]:
            sections.append(("BNS", "3(5)") if use_bns else ("IPC", "34"))

        court = self.courts[did]
        court_id = court["sessions"] if spec["gravity"] == 1 else \
            (court["jmfc"][0] if court["jmfc"] else court["sessions"])
        io_id = (self.ios.get(st_uid) or [None])[0]
        cur.execute("INSERT INTO CaseMaster VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (case_id, crime_no, f"{reg.year}{serial:05d}", reg.isoformat(),
                     io_id, st_uid, cat, spec["gravity"], head_id, subhead_id, 1,
                     court_id, incident.isoformat(sep=" "),
                     (incident + dt.timedelta(hours=1)).isoformat(sep=" "),
                     f"{reg.isoformat()} 10:00",
                     round(st_lat + 0.006, 5), round(st_lon + 0.004, 5), brief))
        cname, cage, cgender = complainant
        comp_id = self.seq.next("compl")
        cur.execute("INSERT INTO ComplainantDetails VALUES (?,?,?,?,?,?,?,?)",
                    (comp_id, case_id, cname, cage, 4, 1, 1,
                     1 if cgender == "M" else 2))
        if victim:
            vname, vage, vgender = victim
            cur.execute("INSERT INTO Victim VALUES (?,?,?,?,?,?)",
                        (self.seq.next("victim"), case_id, vname, vage, vgender, "0"))
        acc_ids = []
        for i, p in enumerate(accused):
            aid = self.seq.next("accused")
            acc_ids.append(aid)
            shown = (shown_names or {}).get(i, p["name"])
            cur.execute("INSERT INTO Accused VALUES (?,?,?,?,?,?)",
                        (aid, case_id, shown, 2026 - p["birth_year"], p["gender"],
                         f"A{i + 1}"))
            cur.execute("INSERT INTO x_er_gold VALUES (?,?,?)", ("Accused", aid, p["pid"]))
            cur.execute("INSERT INTO x_person_case_role VALUES (?,?,?,?,?,?)",
                        (p["pid"], case_id, "accused", aid, 1.0, "generator"))
        for o, (act, sec) in enumerate(sections, 1):
            cur.execute("INSERT OR IGNORE INTO Section VALUES (?,?,?,1)", (act, sec, ""))
            cur.execute("INSERT INTO ActSectionAssociation VALUES (?,?,?,?,?)",
                        (case_id, act, sec, o, o))
        h = incident.hour
        cur.execute("INSERT INTO Inv_OccuranceTime VALUES (?,?,?,?)",
                    (case_id, f"{(h // 3) * 3:02d}-{(h // 3) * 3 + 3:02d}",
                     self.place_ids.get("Street/Road", 2), st_name.replace(" PS", "")))
        for t in mo:
            cur.execute("INSERT INTO x_mo_tag VALUES (?,?,?,?)", (case_id, t, "rule", 1.0))
        if prop:
            kind, desc, identifier, val, recovered = prop
            cur.execute("INSERT INTO x_property VALUES (?,?,?,?,?,?,?)",
                        (self.seq.next("prop"), case_id, kind, desc, identifier,
                         val, recovered))
        if arrest:
            p = accused[arrest["idx"]]
            as_id = self.seq.next("arrest")
            cur.execute("INSERT INTO ArrestSurrender VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (as_id, case_id, 1, arrest["date"], 1, did, st_uid, io_id,
                         court_id, acc_ids[arrest["idx"]], 1, 0))
            cur.execute("INSERT INTO inv_arrestsurrenderaccused VALUES (?,?)",
                        (as_id, acc_ids[arrest["idx"]]))
            if arrest.get("aadhaar_capture"):
                cur.execute("INSERT INTO x_identity_capture VALUES (?,?,?,?,?,?,?)",
                            (case_id, "accused", acc_ids[arrest["idx"]], "aadhaar",
                             p["aadhaar"], id_hash(p["aadhaar"]),
                             arrest["date"]))
            if arrest.get("phone_capture"):
                cur.execute("INSERT INTO x_identity_capture VALUES (?,?,?,?,?,?,?)",
                            (case_id, "accused", acc_ids[arrest["idx"]], "phone",
                             p["phone"], None, arrest["date"]))
        if outcome:
            cstype, csdate = outcome
            cur.execute("INSERT INTO ChargesheetDetails VALUES (?,?,?,?,?)",
                        (self.seq.next("cs"), case_id, csdate, cstype, io_id))
            status = {"A": 2, "B": 3, "C": 4}[cstype]
            cur.execute("UPDATE CaseMaster SET CaseStatusID=? WHERE CaseMasterID=?",
                        (status, case_id))
        return case_id, crime_no


def build_stories(conn, seq, registry, rngf):
    rng = rngf.stream("stories")
    w = StoryWriter(conn, seq, registry)
    manifest = {}

    # ---------------- S1: the Hubballi serial chain-snatcher -----------------
    s1 = w.person("B. Ravi Kumar", "M", 1998, "Dharwad", "738492016453",
                  "9845031277", variants=["Ravikumar B", "Ravi Kumar"],
                  alias="Chikka Ravi")
    spellings = ["B. Ravi Kumar", "Ravikumar B", "Ravi Kumar"]
    plan = [  # (year, month, day, hour, minute, district, station-contains, shown)
        (2024, 2, 11, 6, 15, "Belagavi", None, "Ravi Kumar"),
        (2024, 4, 3, 6, 40, "Belagavi", None, "Ravikumar B"),
        (2024, 8, 19, 7, 5, "Belagavi", None, "Ravikumar B"),
        (2024, 11, 24, 6, 30, "Davanagere", None, "B. Ravi Kumar"),
        (2025, 3, 9, 5, 55, "Davanagere", None, "Ravi Kumar"),
        (2025, 9, 14, 6, 20, "Dharwad", "Hubballi", "Chikka Ravi"),
        (2025, 12, 2, 7, 10, "Dharwad", "Hubballi", "B. Ravi Kumar"),
        (2026, 4, 6, 6, 5, "Dharwad", "Hubballi", "Ravikumar B"),
        (2026, 5, 4, 6, 45, "Dharwad", "Hubballi", "Ravi Kumar"),
        (2026, 5, 26, 5, 50, "Dharwad", "Hubballi", "B. Ravi Kumar"),
        (2026, 6, 14, 6, 25, "Dharwad", "Hubballi", "Ravikumar B"),
    ]
    s1_cases = []
    victims = ["Sharadamma", "Girijamma", "Lalithamma", "Sarojamma", "Nagamma",
               "Parvathamma", "Susheelamma", "Rathnamma", "Gowramma", "Bhagyamma",
               "Kamalamma"]
    for i, (y, m, d, hh, mm, district, contains, shown) in enumerate(plan):
        grams = rng.choice([20, 25, 30, 40])
        vict = victims[i]
        st = w.station(district, contains=contains)
        brief = (f"{vict}, aged {rng.randint(48, 66)}, reported that on {y}-{m:02d}-"
                 f"{d:02d} at about {hh:02d}{mm:02d} hrs, while she was on her "
                 f"morning walk near {st[1].replace(' PS', '')}, a pillion rider on "
                 f"a dark two-wheeler approaching from behind snatched her gold "
                 f"chain of {grams} grams and the riders sped away towards the "
                 f"highway. The rider wore a full-face helmet; the pillion was a "
                 f"slim male in his twenties. Similar method noticed in earlier "
                 f"cases. MO: two-wheeler-pillion-snatch, morning-walk-target, "
                 f"gold-chain-snatch.")
        arrest = None
        outcome = None
        if i == 2:      # arrested in Belagavi 2024, Aadhaar captured
            arrest = {"idx": 0, "date": "2024-09-02", "aadhaar_capture": True}
            outcome = ("A", "2024-11-20")
        if i == 5:      # arrested under his street alias in 2025 — same Aadhaar
            arrest = {"idx": 0, "date": "2025-09-25", "aadhaar_capture": True,
                      "phone_capture": True}
            outcome = ("A", "2025-12-18")
        cid, cno = w.case("snatching", district, st,
                          dt.datetime(y, m, d, hh, mm), brief, accused=[s1],
                          shown_names={0: shown},
                          complainant=(vict, rng.randint(48, 66), "F"),
                          victim=(vict, rng.randint(48, 66), "F"),
                          mo=["two-wheeler-pillion-snatch", "morning-walk-target",
                              "gold-chain-snatch"],
                          prop=("gold-jewellery", f"gold chain of {grams} grams",
                                None, grams * GOLD_RATE_PER_GRAM, 1 if i == 2 else 0),
                          arrest=arrest, outcome=outcome, delay_days=0)
        s1_cases.append(cno)
    manifest["S1_serial_snatcher"] = {"person_id": s1["pid"], "alias": "Chikka Ravi",
                                      "spellings": spellings, "cases": s1_cases}

    # ---------------- S2: the vehicle-theft ring + the fence -----------------
    thieves = [w.person(n, "M", by, d, a, p) for n, by, d, a, p in [
        ("Suresh Naik", 1996, "Bengaluru Urban", "634829105672", "9902214531"),
        ("Kiran Gowda", 1999, "Bengaluru Urban", "645910238467", "9880125634"),
        ("Manju Shetty", 1994, "Tumakuru", "656012349578", "9845762310"),
        ("Prakash Raju", 1997, "Mysuru", "667123450689", "9902458761"),
        ("Abdul Rafiq", 1995, "Bengaluru Urban", "678234561790", "9738124590"),
        ("Venkatesh Murthy", 1992, "Mandya", "689345672801", "9845098213"),
    ]]
    fence = w.person("Salim Mujawar", "M", 1985, "Bengaluru Urban",
                     "690456783912", "9900817245")
    pairs = [(0, 1), (2, 3), (4, 5), (0, 2), (1, 4), (3, 5), (0, 5), (2, 4),
             (1, 3), (0, 4)]
    ring_plan = [("Bengaluru Urban", 2023, 5), ("Bengaluru Urban", 2023, 9),
                 ("Tumakuru", 2024, 1), ("Bengaluru Urban", 2024, 4),
                 ("Mysuru", 2024, 8), ("Mandya", 2024, 12),
                 ("Bengaluru Urban", 2025, 3), ("Tumakuru", 2025, 7),
                 ("Mysuru", 2025, 11), ("Bengaluru Urban", 2026, 3)]
    s2_cases = []
    for i, ((a, b), (district, y, m)) in enumerate(zip(pairs, ring_plan)):
        reg = (f"KA-{rng.randint(1, 65):02d}-{chr(rng.randint(65, 90))}"
               f"{chr(rng.randint(65, 90))}-{rng.randint(1000, 9999)}")
        acc = [thieves[a], thieves[b]] + ([fence] if i in (1, 4, 6, 9) else [])
        st = w.station(district)
        brief = (f"Complainant reported that his motorcycle bearing reg no {reg} "
                 f"parked near {st[1].replace(' PS', '')} was stolen during the "
                 f"night. Investigation revealed an organised group lifting "
                 f"two-wheelers using duplicate keys and disposing them through a "
                 f"known receiver of stolen property. MO: two-wheeler-lifting, "
                 f"duplicate-key, organised-ring.")
        arrest = {"idx": 0, "date": f"{y}-{m:02d}-27", "aadhaar_capture": True,
                  "phone_capture": True} if i in (3, 6, 9) else None
        cid, cno = w.case("vehicle_theft", district, st,
                          dt.datetime(y, m, rng.randint(2, 20), 1, 30), brief,
                          accused=acc,
                          complainant=("K. Nagesh", 38, "M"),
                          mo=["two-wheeler-lifting", "duplicate-key", "organised-ring"],
                          prop=("vehicle", f"motorcycle reg no {reg}", reg,
                                rng.choice([45000, 60000, 75000]),
                                1 if i in (3, 6) else 0),
                          arrest=arrest,
                          outcome=("A", f"{y}-{m + 2 if m < 11 else 12:02d}-15")
                          if i in (3, 6) else None,
                          delay_days=1)
        s2_cases.append(cno)
    manifest["S2_vehicle_ring"] = {
        "member_pids": [t["pid"] for t in thieves], "fence_pid": fence["pid"],
        "cases": s2_cases}

    # ---------------- S3: investment-app fraud (finance trail in 1f) ---------
    mule_names = [("Ramesh Angadi", "Kalaburagi"), ("Fayaz Sheikh", "Ballari"),
                  ("Somashekar Naik", "Davanagere"), ("Lokesh Reddy", "Kolar")]
    mules = [w.person(n, "M", 1990 + i, d,
                      f"70{i}56789012{i}", f"96325870{i}1")
             for i, (n, d) in enumerate(mule_names)] + [fence]
    s3_cases = []
    fraud_districts = ["Bengaluru Urban", "Bengaluru Urban", "Bengaluru Urban",
                       "Mysuru", "Dharwad", "Dakshina Kannada", "Belagavi",
                       "Kalaburagi", "Shivamogga", "Tumakuru", "Bengaluru Urban",
                       "Bengaluru Urban", "Hassan", "Ballari", "Bengaluru Urban"]
    for i, district in enumerate(fraud_districts):
        y, m = (2025, 3 + i) if i < 9 else (2026, i - 8)
        amount = rng.choice([180000, 350000, 520000, 900000, 1500000])
        named = i in (12, 14)          # two cases where mule holders were traced
        acc = [mules[i % 4]] if named else []
        st = w.station(district, kind="cen")
        brief = (f"Complainant reported that he was added to a WhatsApp group "
                 f"promoting the 'GoldenBull Trading App' promising 30% monthly "
                 f"returns, and was induced to transfer Rs. {amount} in tranches "
                 f"to bank accounts provided in the app chat. Withdrawals were "
                 f"blocked and the app went offline. Amounts traced to mule "
                 f"accounts. MO: investment-app-fraud. NCRP complaint filed.")
        incident = dt.datetime(y, min(m, 12), rng.randint(2, 20), 14, 0)
        cid, cno = w.case("cyber_fraud", district, st, incident,
                          brief, accused=acc,
                          complainant=("Complainant", rng.randint(28, 55), "M"),
                          mo=["investment-app-fraud"],
                          prop=("cash", f"defrauded amount Rs. {amount}", None,
                                amount, 0),
                          arrest={"idx": 0,
                                  "date": min(incident.date() + dt.timedelta(days=40),
                                              dt.date(2026, 6, 28)).isoformat(),
                                  "aadhaar_capture": True, "phone_capture": True}
                          if named else None,
                          delay_days=rng.randint(2, 9))
        s3_cases.append(cno)
    manifest["S3_investment_fraud"] = {
        "mule_pids": [p["pid"] for p in mules], "fence_pid": fence["pid"],
        "app_name": "GoldenBull Trading App", "cases": s3_cases}

    # ---------------- S4: escalating domestic-violence offender --------------
    s4 = w.person("Manjunatha D", "M", 1988, "Mysuru", "701234598762", "9741032856")
    esc = [("cruelty_498a", 2023, 4, "cruelty and dowry harassment"),
           ("hurt", 2024, 6, "assault causing injuries"),
           ("intimidation", 2025, 2, "criminal intimidation with dire threats"),
           ("attempt_murder", 2026, 3, "attempt on her life by strangulation")]
    s4_cases = []
    for i, (ctype, y, m, phrase) in enumerate(esc):
        st = w.station("Mysuru", kind="women" if i < 2 else "regular")
        brief = (f"Sowmya, wife of the accused Manjunatha D, reported {phrase} at "
                 f"their residence. This is the {['first', 'second', 'third', 'fourth'][i]} "
                 f"case reported against the same person by the same victim, showing "
                 f"clear escalation. MO: domestic-violence, escalating-pattern.")
        cid, cno = w.case(ctype, "Mysuru", st, dt.datetime(y, m, 10, 21, 0), brief,
                          accused=[s4], complainant=("Sowmya", 32, "F"),
                          victim=("Sowmya", 32, "F"),
                          mo=["domestic-violence", "escalating-pattern"],
                          arrest={"idx": 0, "date": f"{y}-{m:02d}-14",
                                  "aadhaar_capture": i >= 1} if i in (1, 3) else None,
                          outcome=("A", f"{y}-{m + 3:02d}-20") if i < 3 else None,
                          delay_days=2)
        s4_cases.append(cno)
    manifest["S4_escalating_offender"] = {"person_id": s4["pid"], "cases": s4_cases}

    # ---------------- S5: the serial false complainant ------------------------
    s5_cases = []
    for i, (ctype, y) in enumerate([("trespass", 2022), ("mischief", 2022),
                                    ("intimidation", 2023), ("trespass", 2024),
                                    ("mischief", 2024), ("intimidation", 2025)]):
        st = w.station("Tumakuru")
        neighbour = w.person(f"Neighbour {i + 1} Gowda", "M", 1975 + i, "Tumakuru",
                             f"71234567890{i}", f"973812456{i}")
        brief = (f"Gangamma reported that her neighbour committed {ctype.replace('_', ' ')} "
                 f"against her property. Investigation found the allegation "
                 f"unsubstantiated; final report filed as false case. This is one of "
                 f"several similar complaints by the same complainant against "
                 f"neighbours. MO: neighbour-dispute.")
        cid, cno = w.case(ctype, "Tumakuru", st,
                          dt.datetime(y, 2 + i, 15, 11, 0), brief,
                          accused=[neighbour], complainant=("Gangamma", 58, "F"),
                          mo=["neighbour-dispute"],
                          outcome=("B", f"{y}-{8 + (i % 3):02d}-10"), delay_days=1)
        s5_cases.append(cno)
    manifest["S5_false_complainant"] = {"complainant": "Gangamma", "cases": s5_cases}

    conn.commit()
    EXPORT_DIR.mkdir(exist_ok=True)
    (EXPORT_DIR / "stories.json").write_text(json.dumps(manifest, indent=2))
    return {"stories": len(manifest), "story_cases": len(w.case_ids),
            "case_ids": w.case_ids, "manifest": manifest}
