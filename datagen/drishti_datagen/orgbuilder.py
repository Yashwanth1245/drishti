"""Builds the real Karnataka police organization into the database.

Creates States, the 31 Districts, the 7 Ranges, 6 City Commissionerates + KGF
police district, ~1,100 Police Stations (real names where researched, real
taluk-derived names elsewhere, plus Women PS / CEN PS per policing unit),
Courts, Ranks/Designations and a realistic Employee roster. Also writes
x_unit_geo so every station has map coordinates (taluk-anchored offsets from
the district HQ — see config.DISTRICT_HQ_COORDS for accuracy notes).
"""

from .config import (BENGALURU_CITY_EXTRA_STATIONS, BENGALURU_CITY_STATIONS,
                     BENGALURU_URBAN_DISTRICT_STATIONS, COMMISSIONERATE_DISTRICT,
                     COMMISSIONERATE_STATIONS, EMPLOYEE_FEMALE_RATE,
                     MAX_DISTRICT_STATIONS, MIN_DISTRICT_STATIONS,
                     POP_PER_STATION, SMALL_STATION_STAFF, STATION_STAFF,
                     BLOOD_GROUPS)
from .util import stable_offset, weighted

NEIGHBOR_STATES = ["Maharashtra", "Andhra Pradesh", "Tamil Nadu", "Telangana",
                   "Kerala", "Goa"]

RANKS = [(1, "DGP", 1), (2, "ADGP", 2), (3, "IGP", 3), (4, "DIGP", 4),
         (5, "SP", 5), (6, "Addl. SP", 6), (7, "DySP", 7), (8, "PI", 8),
         (9, "PSI", 9), (10, "ASI", 10), (11, "Head Constable", 11),
         (12, "Police Constable", 12)]

DESIGNATIONS = [(1, "DG&IGP"), (2, "Commissioner of Police"), (3, "DIG (Range)"),
                (4, "Superintendent of Police"), (5, "Deputy Commissioner of Police"),
                (6, "SDPO"), (7, "Circle Inspector"), (8, "SHO"),
                (9, "Investigating Officer"), (10, "Station Writer"),
                (11, "Beat Constable"), (12, "ACP")]

UNIT_TYPES = [(1, "State Police Headquarters", "State", 1),
              (2, "Range", "State", 2),
              (3, "City Commissionerate", "City", 3),
              (4, "District Police", "District", 3),
              (5, "Police Station", "City", 6),
              (6, "Women Police Station", "District", 6),
              (7, "CEN Police Station", "District", 6),
              (8, "Traffic Police Station", "City", 6)]

RANK_DESIGNATION = {"PI": 8, "PSI": 9, "ASI": 10, "HC": 11, "PC": 11}
RANK_ID = {name: rid for rid, name, _ in RANKS}
RANK_ID["HC"] = RANK_ID["Head Constable"]
RANK_ID["PC"] = RANK_ID["Police Constable"]
RANK_AGE = {"DGP": (54, 58), "ADGP": (52, 57), "IGP": (48, 56), "DIGP": (45, 54),
            "SP": (35, 50), "Addl. SP": (34, 50), "DySP": (30, 52), "PI": (35, 54),
            "PSI": (25, 42), "ASI": (30, 52), "HC": (28, 54), "PC": (22, 40)}

KGF_STATIONS = ["Robertsonpet PS", "Andersonpet PS", "KGF Town PS",
                "Marikuppam PS", "Bethamangala PS"]

KA_LAT = (11.6, 18.4)   # clamp box so jittered points stay inside Karnataka-ish
KA_LON = (74.1, 78.5)


def _clamp(lat, lon):
    return (min(max(lat, KA_LAT[0]), KA_LAT[1]), min(max(lon, KA_LON[0]), KA_LON[1]))


def build_org(conn, ref, rngf, seq, name_factory):
    cur = conn.cursor()
    rng = rngf.stream("org")

    # ---- states / districts -------------------------------------------------
    cur.execute("INSERT INTO State VALUES (1,'Karnataka',1,1)")
    for i, s in enumerate(NEIGHBOR_STATES, 2):
        cur.execute("INSERT INTO State VALUES (?,?,1,1)", (i, s))

    district_id = {}
    for i, d in enumerate(ref["districts"], 1):
        did = 1000 + i
        district_id[d["name"]] = did
        cur.execute("INSERT INTO District VALUES (?,?,1,1)", (did, d["name"]))

    cur.executemany("INSERT INTO UnitType VALUES (?,?,?,?,1)", UNIT_TYPES)
    cur.executemany("INSERT INTO Rank VALUES (?,?,?,1)", RANKS)
    cur.executemany("INSERT INTO Designation VALUES (?,?,1,?)",
                    [(i, n, i) for i, n in DESIGNATIONS])

    districts_by_name = {d["name"]: d for d in ref["districts"]}
    hq_to_district = {d["hq"]: d["name"] for d in ref["districts"]}
    hq_to_district.setdefault("Bengaluru", "Bengaluru Urban")
    hq_to_district.setdefault("Mangaluru", "Dakshina Kannada")

    def new_unit(name, type_id, parent, dname):
        uid = seq.next("unit")
        cur.execute("INSERT INTO Unit VALUES (?,?,?,?,1,1,?,1)",
                    (uid, name, type_id, parent, district_id[dname]))
        return uid

    # ---- HQ, ranges, policing units ----------------------------------------
    hq_unit = new_unit("State Police Headquarters, Bengaluru", 1, None, "Bengaluru Urban")

    range_unit, district_range = {}, {}
    for r in ref["police"]["ranges"]:
        dname = hq_to_district.get(r.get("hq", ""), "Bengaluru Urban")
        range_unit[r["name"]] = new_unit(f"{r['name']}, {r.get('hq', '')}", 2, hq_unit, dname)
        for member in r.get("districts", []):
            base = member.split(" (")[0].strip()
            if base in districts_by_name:
                district_range[base] = r["name"]
    central = range_unit.get("Central Range", hq_unit)

    policing_units = []   # (unit_id, district_name, kind, target_stations, real_names)
    examples = {e["unit"]: e["stations"] for e in ref["police"]["stationExamples"]}

    for comm, dname in COMMISSIONERATE_DISTRICT.items():
        uid = new_unit(comm, 3, hq_unit, dname)
        target = BENGALURU_CITY_STATIONS if comm == "Bengaluru City Police" \
            else COMMISSIONERATE_STATIONS[comm]
        real = list(examples.get(comm, []))
        if comm == "Bengaluru City Police":
            seen = {s.lower() for s in real}
            real += [s for s in BENGALURU_CITY_EXTRA_STATIONS if s.lower() not in seen]
        policing_units.append((uid, dname, "commissionerate", target, real))

    for d in ref["districts"]:
        dname = d["name"]
        rng_name = district_range.get(dname)
        parent = range_unit.get(rng_name, central)
        uid = new_unit(f"{dname} District Police", 4, parent, dname)
        if dname == "Bengaluru Urban":
            target = BENGALURU_URBAN_DISTRICT_STATIONS
        else:
            target = max(MIN_DISTRICT_STATIONS,
                         min(MAX_DISTRICT_STATIONS, round(d["popEstimate"] / POP_PER_STATION)))
            if dname in COMMISSIONERATE_DISTRICT.values():
                comm = next(c for c, dn in COMMISSIONERATE_DISTRICT.items() if dn == dname)
                comm_n = BENGALURU_CITY_STATIONS if comm == "Bengaluru City Police" \
                    else COMMISSIONERATE_STATIONS[comm]
                target = max(10, target - comm_n)
            target = min(target, 5 * len(d["taluks"]) + 2)
        # real researched names exist for a few district units (Shivamogga, Tumakuru)
        real = [s for key, s in
                ((k, v) for k, v in examples.items()) if key.startswith(dname)]
        real = real[0] if real else []
        policing_units.append((uid, dname, "district", target, list(real)))

    kgf_unit = new_unit("Kolar Gold Field (KGF) Police District", 4, central, "Kolar")
    policing_units.append((kgf_unit, "Kolar", "kgf", len(KGF_STATIONS), KGF_STATIONS))

    # ---- stations + coordinates ---------------------------------------------
    station_rows, geo_rows = [], []

    def add_station(name, type_id, parent_uid, dname, lat, lon):
        uid = seq.next("unit")
        lat, lon = _clamp(lat, lon)
        station_rows.append((uid, name, type_id, parent_uid, 1, 1, district_id[dname], 1))
        geo_rows.append((uid, round(lat, 5), round(lon, 5)))
        return uid

    for uid, dname, kind, target, real in policing_units:
        d = districts_by_name[dname]
        hq_lat, hq_lon = d["hq_coords"]
        names = list(dict.fromkeys(real))[:target]
        if len(names) < target:
            if kind == "commissionerate":
                city = dname if dname != "Dakshina Kannada" else "Mangaluru"
                pool = [f"{city} {suffix} PS" for suffix in
                        ["East", "West", "North", "South", "Market", "Extension",
                         "Camp", "Gandhi Nagar", "Industrial Area", "Railway"]]
                pool += [f"{city} Traffic PS {i}" for i in range(1, 8)]
            else:
                pool = [f"{t} Town PS" for t in d["taluks"]] + \
                       [f"{t} Rural PS" for t in d["taluks"]] + \
                       [f"{t} Traffic PS" for t in d["taluks"]] + \
                       [f"{t} East PS" for t in d["taluks"]] + \
                       [f"{t} West PS" for t in d["taluks"]]
            for cand in pool:
                if len(names) >= target:
                    break
                if cand not in names:
                    names.append(cand)
        for n in names:
            ttype = 8 if "Traffic" in n else 5
            if kind == "commissionerate":
                dlat, dlon = stable_offset(n, 0.005, 0.09)
                jl = rng.uniform(-0.004, 0.004)
            else:
                anchor = next((t for t in d["taluks"] if n.startswith(t)), d["hq"])
                dlat, dlon = stable_offset(f"{dname}:{anchor}", 0.02, 0.42)
                jl = rng.uniform(-0.015, 0.015)
            add_station(n, ttype, uid, dname, hq_lat + dlat + jl, hq_lon + dlon + jl)
        # one Women PS + one CEN PS per policing unit (real KSP structure)
        label = dname if kind != "commissionerate" else dname + " City"
        if kind != "kgf":
            add_station(f"{label} Women PS", 6, uid, dname,
                        hq_lat + rng.uniform(-0.01, 0.01), hq_lon + rng.uniform(-0.01, 0.01))
            add_station(f"{label} CEN Crime PS", 7, uid, dname,
                        hq_lat + rng.uniform(-0.01, 0.01), hq_lon + rng.uniform(-0.01, 0.01))

    cur.executemany("INSERT INTO Unit VALUES (?,?,?,?,?,?,?,?)", station_rows)
    cur.executemany("INSERT INTO x_unit_geo VALUES (?,?,?)", geo_rows)

    # ---- socio-economic indicators (census reference -> in-DB for dashboards) --
    cur.executemany("INSERT INTO x_district_indicators VALUES (?,?,?,?,?,?)",
                    [(district_id[d["name"]], d["pop2011"], d["popEstimate"],
                      d["urbanPct"], d["literacyPct"], d["sexRatio"])
                     for d in ref["districts"]])

    # ---- courts --------------------------------------------------------------
    for d in ref["districts"]:
        cid = seq.next("court")
        cur.execute("INSERT INTO Court VALUES (?,?,?,1,1)",
                    (cid, f"{d['name']} District & Sessions Court", district_id[d["name"]]))
        for t in d["taluks"]:
            cid = seq.next("court")
            cur.execute("INSERT INTO Court VALUES (?,?,?,1,1)",
                        (cid, f"JMFC Court, {t}", district_id[d["name"]]))

    # ---- employees ------------------------------------------------------------
    emp_rows = []

    def new_employee(unit_id, dname, rank_name, desig_id, force_female=False):
        eid = seq.next("emp")
        female = force_female or rng.random() < EMPLOYEE_FEMALE_RATE
        p = name_factory.person(rng, dname, gender="F" if female else "M")
        lo, hi = RANK_AGE[rank_name]
        age = rng.randint(lo, hi)
        dob_year = 2026 - age
        dob = f"{dob_year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        appt = f"{dob_year + rng.randint(21, 27)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        emp_rows.append((eid, district_id[dname], unit_id, RANK_ID[rank_name], desig_id,
                         str(1000000 + eid), p["display"], dob, 2 if female else 1,
                         weighted(rng, [(i + 1, w) for i, (_, w) in enumerate(BLOOD_GROUPS)]),
                         1 if rng.random() < 0.01 else 0, appt))
        return eid

    new_employee(hq_unit, "Bengaluru Urban", "DGP", 1)
    for _ in range(4):
        new_employee(hq_unit, "Bengaluru Urban", "ADGP", 1)
    for r in ref["police"]["ranges"]:
        dname = hq_to_district.get(r.get("hq", ""), "Bengaluru Urban")
        new_employee(range_unit[r["name"]], dname, "DIGP", 3)
        for _ in range(2):
            new_employee(range_unit[r["name"]], dname, "DySP", 6)
    for uid, dname, kind, _, _ in policing_units:
        if kind == "commissionerate":
            new_employee(uid, dname, "IGP", 2)
            for _ in range(4):
                new_employee(uid, dname, "SP", 5)
            for _ in range(8):
                new_employee(uid, dname, "DySP", 12)
        else:
            new_employee(uid, dname, "SP", 4)
            new_employee(uid, dname, "Addl. SP", 4)
            for _ in range(4):
                new_employee(uid, dname, "DySP", 6)

    cur.execute("SELECT UnitID, UnitName, TypeID, DistrictID FROM Unit WHERE TypeID >= 5")
    did_to_name = {v: k for k, v in district_id.items()}
    for uid, uname, type_id, did in cur.fetchall():
        dname = did_to_name[did]
        women = type_id == 6
        staff = STATION_STAFF if (type_id in (5, 7) and "Rural" not in uname) \
            else SMALL_STATION_STAFF
        for rank_name, count in staff:
            for _ in range(count):
                new_employee(uid, dname, rank_name,
                             8 if rank_name == "PI" else RANK_DESIGNATION[rank_name],
                             force_female=women)

    cur.executemany("INSERT INTO Employee VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", emp_rows)
    conn.commit()

    return {"districts": len(district_id), "units": seq.current("unit"),
            "stations": len(station_rows), "employees": len(emp_rows),
            "courts": seq.current("court")}
