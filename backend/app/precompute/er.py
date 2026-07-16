"""Entity resolution: turn ~245k unlinked Accused rows into person entities.

Three passes, strictly ordered from certain to inferred:
  1. HARD LINKS — identical identity-hash (Aadhaar captured at two arrests,
     even under different names: the alias-exposure case) or identical phone.
  2. RARE-NAME ATTRIBUTE MATCH — only within name-skeleton blocks small enough
     that the name itself is distinctive (<= ER_RARE_BLOCK_MAX rows statewide):
     near-exact name + tight age + geography (+ MO bonus). Common-name blocks
     are skipped entirely: with only name/age/gender in the Accused table,
     two "Nagaraju, 28, Mysuru" rows are genuinely indistinguishable, and
     merging them would be profiling, not resolution. Rows sharing a case
     NEVER merge (A1 and A2 of one FIR are different people by definition).
  3. MO LINKAGE — behavioral pass for everyone, including common names:
     near-identical names, compatible ages, and the same RARE modus operandi
     (repeatedly on both sides, or once each within the same district). This
     is the "repeat offender across jurisdictions" capability.

Every merge stores its basis (explainability), and the whole partition is
scored against the generator's ground truth (x_er_gold) — pairwise precision
and recall go into x_metric for the UI to display.

Outputs: x_entity, x_entity_member (created here; app-owned tables).
"""

import json
import math
import re
import time
from collections import Counter, defaultdict

from rapidfuzz import fuzz

from ..config import (ER_AGE_W, ER_AGE_WINDOW, ER_COMMONNESS_CAP, ER_GEO_FAR,
                      ER_GEO_NEIGHBOR, ER_GEO_SAME, ER_MERGE_MAX_AGE_GAP,
                      ER_MERGE_THRESHOLD, ER_MIN_NAME_RATIO, ER_MO_BONUS,
                      ER_MO_LINK_MIN_EACH, ER_MO_LINK_NAME_RATIO,
                      ER_MO_RARE_FREQ, ER_NAME_W, ER_RARE_BLOCK_MAX,
                      ER_SUBHEAD_BONUS)
from ..db import district_neighbors

VOWELS = set("aeiou")
TOKEN_ALIASES = {"md": "mohammed", "mohd": "mohammed", "mohamed": "mohammed",
                 "mohammad": "mohammed", "muhammad": "mohammed"}

DDL = """
CREATE TABLE IF NOT EXISTS x_entity (
    entity_id        INTEGER PRIMARY KEY,
    canonical_name   TEXT,
    gender           TEXT,
    birth_year_est   INTEGER,
    home_district_id INTEGER,
    n_cases          INTEGER,
    n_rows           INTEGER,
    first_seen       TEXT,
    last_seen        TEXT,
    risk_score       REAL,
    risk_factors     TEXT
);
CREATE TABLE IF NOT EXISTS x_entity_member (
    entity_id       INTEGER,
    AccusedMasterID INTEGER PRIMARY KEY,
    CaseMasterID    INTEGER,
    shown_name      TEXT,
    match_basis     TEXT
);
CREATE INDEX IF NOT EXISTS idx_member_entity ON x_entity_member(entity_id);
CREATE INDEX IF NOT EXISTS idx_member_case ON x_entity_member(CaseMasterID);
CREATE TABLE IF NOT EXISTS x_metric (key TEXT PRIMARY KEY, value TEXT);
"""


def normalize(name: str) -> str:
    s = re.sub(r"[^a-z ]", " ", (name or "").lower())
    toks = [TOKEN_ALIASES.get(t, t) for t in s.split() if len(t) > 2]
    return " ".join(toks) if toks else s.replace(" ", "") or "x"


def skeleton(norm: str) -> str:
    joined = norm.replace(" ", "")
    cons = "".join(ch for ch in joined if ch not in VOWELS)
    return (cons or joined)[:6]


def name_sim(a, b) -> int:
    """Similarity robust to compound joins: 'Ravi Kumar' vs 'Ravikumar' = 100."""
    return max(fuzz.token_sort_ratio(a["norm"], b["norm"]),
               fuzz.ratio(a["joined"], b["joined"]))


class UnionFind:
    def __init__(self):
        self.parent = {}
        self.basis = {}                 # child-root -> why it joined its parent

    def find(self, x):
        root = x
        while self.parent.get(root, root) != root:
            root = self.parent[root]
        while self.parent.get(x, x) != x:            # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b, basis):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.parent[rb] = ra
        self.basis[rb] = basis
        return True


def _load_rows(conn):
    rows = {}
    for (aid, cid, name, age, gender, did, year, subhead) in conn.execute(
            "SELECT a.AccusedMasterID, a.CaseMasterID, a.AccusedName, a.AgeYear, "
            "UPPER(SUBSTR(COALESCE(a.GenderID,'M'),1,1)), u.DistrictID, "
            "CAST(substr(c.CrimeRegisteredDate,1,4) AS INT), c.CrimeMinorHeadID "
            "FROM Accused a JOIN CaseMaster c ON c.CaseMasterID=a.CaseMasterID "
            "JOIN Unit u ON u.UnitID=c.PoliceStationID"):
        norm = normalize(name)
        rows[aid] = {"aid": aid, "case": cid, "name": name, "norm": norm,
                     "joined": norm.replace(" ", ""),
                     "skel": skeleton(norm), "gender": gender or "M",
                     "birth": year - (age or 30), "district": did,
                     "subhead": subhead, "tags": frozenset()}
    tag_map = defaultdict(set)
    for cid, tag in conn.execute("SELECT CaseMasterID, tag FROM x_mo_tag"):
        tag_map[cid].add(tag)
    for r in rows.values():
        r["tags"] = frozenset(tag_map.get(r["case"], ()))
    return rows


def build(conn):
    t0 = time.time()
    conn.executescript(DDL)
    cur = conn.cursor()
    cur.execute("DELETE FROM x_entity")
    cur.execute("DELETE FROM x_entity_member")

    rows = _load_rows(conn)
    neighbors = district_neighbors(conn)
    uf = UnionFind()
    stats = Counter()

    # ---- pass 1: hard identity links ------------------------------------
    by_hash, by_phone = defaultdict(list), defaultdict(list)
    for aid, id_type, value, id_hash in conn.execute(
            "SELECT source_row_id, id_type, id_value, id_hash "
            "FROM x_identity_capture WHERE role='accused'"):
        if aid not in rows:
            continue
        if id_type == "aadhaar" and id_hash:
            by_hash[id_hash].append(aid)
        elif id_type == "phone" and value:
            by_phone[value].append(aid)
    for group, basis in ((by_hash, "aadhaar-hash"), (by_phone, "shared-phone")):
        for members in group.values():
            for other in members[1:]:
                if uf.union(members[0], other, basis):
                    stats[f"hard:{basis}"] += 1

    # ---- pass 2: rare-name attribute matching ------------------------------
    blocks = defaultdict(list)
    for r in rows.values():
        blocks[(r["skel"], r["gender"])].append(r)

    for (skel, _g), members in blocks.items():
        n = len(members)
        if n < 2:
            continue
        if n > ER_RARE_BLOCK_MAX:
            stats["blocks:common_skipped"] += 1     # name not distinctive
            continue
        penalty = min(ER_COMMONNESS_CAP, 0.05 * math.log10(max(n, 2)))
        members.sort(key=lambda r: r["birth"])
        for i in range(n):
            a = members[i]
            for b in members[i + 1:]:
                dy = b["birth"] - a["birth"]
                if dy > ER_MERGE_MAX_AGE_GAP:
                    break
                if a["case"] == b["case"]:          # same-FIR rows: never merge
                    continue
                if uf.find(a["aid"]) == uf.find(b["aid"]):
                    continue
                ratio = name_sim(a, b)
                if ratio < ER_MIN_NAME_RATIO:
                    continue
                if a["district"] == b["district"]:
                    geo = ER_GEO_SAME
                elif b["district"] in neighbors.get(a["district"], ()):
                    geo = ER_GEO_NEIGHBOR
                else:
                    geo = ER_GEO_FAR
                shared_mo = bool(a["tags"] & b["tags"])
                score = (ratio / 100.0) * ER_NAME_W \
                    + (1 - dy / (ER_AGE_WINDOW + 1)) * ER_AGE_W + geo - penalty
                if shared_mo:
                    score += ER_MO_BONUS
                if a["subhead"] and a["subhead"] == b["subhead"]:
                    score += ER_SUBHEAD_BONUS
                if score >= ER_MERGE_THRESHOLD:
                    basis = (f"rare-name {ratio}% + age d{dy} + "
                             f"{'same' if geo == ER_GEO_SAME else 'near' if geo == ER_GEO_NEIGHBOR else 'far'}-district"
                             + (" + shared-MO" if shared_mo else ""))
                    if uf.union(a["aid"], b["aid"], basis):
                        stats["fuzzy:merged"] += 1

    # ---- pass 3: cross-jurisdiction MO linkage ---------------------------
    total_cases = conn.execute("SELECT COUNT(*) FROM CaseMaster").fetchone()[0]
    tag_freq = Counter()
    for cid, tag in conn.execute("SELECT CaseMasterID, tag FROM x_mo_tag"):
        tag_freq[tag] += 1
    rare = {t for t, c in tag_freq.items() if c / total_cases < ER_MO_RARE_FREQ}
    # ultra-rare signatures (well under 0.3% of cases) are near-fingerprints:
    # they may bridge districts and mono-token names where ordinary rare tags
    # may not.
    ultra = {t for t, c in tag_freq.items() if c / total_cases < 0.003}

    # Two rounds so weak (same-district) merges can consolidate singletons
    # into clusters strong enough for cross-district linkage in round 2 —
    # exactly how an analyst would work: local series first, then across
    # jurisdictions.
    for _round in (1, 2):
        clusters = defaultdict(list)
        for r in rows.values():
            clusters[uf.find(r["aid"])].append(r)
        # group candidates by (name skeleton, gender, rare tag): "Ravi Kumars
        # who do pillion snatching" is a tiny group even when "Ravi Kumar" is
        # one of the most common names in the state.
        by_key = defaultdict(list)
        for root, mem in clusters.items():
            rare_tags = Counter()
            for r in mem:
                for t in r["tags"] & rare:
                    rare_tags[t] += 1
            if not rare_tags:
                continue
            home = Counter(r["district"] for r in mem).most_common(1)[0][0]
            births = sorted(r["birth"] for r in mem)
            entry = (root, mem[0], rare_tags, home, births[len(births) // 2])
            for t in rare_tags:
                by_key[(mem[0]["skel"], mem[0]["gender"], t)].append(entry)
        for (_s, _g, tag), group in by_key.items():
            if len(group) > 50:      # even tag-scoped, too ambiguous — skip
                stats["mo:group_skipped"] += 1
                continue
            for i in range(len(group)):
                for k in range(i + 1, len(group)):
                    ra, rep_a, ta, home_a, birth_a = group[i]
                    rb, rep_b, tb, home_b, birth_b = group[k]
                    if uf.find(ra) == uf.find(rb):
                        continue
                    if abs(birth_a - birth_b) > ER_AGE_WINDOW:
                        continue
                    # strong: this rare MO repeatedly on BOTH sides (any geo)
                    # semi:   ultra-rare MO, repeatedly on ONE side (any geo)
                    # weak:   round 1, same district, once each — but only for
                    #         multi-token names or ultra-rare signatures
                    #         (mono-token common names chain into blobs)
                    strong = (ta[tag] >= ER_MO_LINK_MIN_EACH
                              and tb[tag] >= ER_MO_LINK_MIN_EACH)
                    semi = tag in ultra and max(ta[tag], tb[tag]) >= ER_MO_LINK_MIN_EACH
                    weak = (_round == 1 and home_a == home_b
                            and (" " in rep_a["norm"] or tag in ultra))
                    if not (strong or semi or weak):
                        continue
                    ratio = name_sim(rep_a, rep_b)
                    if ratio >= ER_MO_LINK_NAME_RATIO:
                        uf.union(ra, rb, f"mo-linkage:{tag} + name {ratio}%")
                        stats["mo:merged"] += 1

    # ---- materialize entities --------------------------------------------
    final = defaultdict(list)
    for r in rows.values():
        final[uf.find(r["aid"])].append(r)

    date_of = dict(conn.execute(
        "SELECT CaseMasterID, CrimeRegisteredDate FROM CaseMaster"))
    ent_rows, mem_rows = [], []
    for eid, (_root, mem) in enumerate(sorted(final.items()), 1):
        names = Counter(m["name"] for m in mem)
        canonical = max(names.items(), key=lambda kv: (kv[1], len(kv[0])))[0]
        births = sorted(m["birth"] for m in mem)
        cases = {m["case"] for m in mem}
        dates = sorted(date_of[c] for c in cases)
        home = Counter(m["district"] for m in mem).most_common(1)[0][0]
        ent_rows.append((eid, canonical, mem[0]["gender"],
                         births[len(births) // 2], home, len(cases), len(mem),
                         dates[0], dates[-1], None, None))
        for m in mem:
            root = uf.find(m["aid"])
            basis = uf.basis.get(m["aid"], "unlinked" if len(mem) == 1
                                 else "cluster-root")
            mem_rows.append((eid, m["aid"], m["case"], m["name"], basis))
    cur.executemany("INSERT INTO x_entity VALUES (?,?,?,?,?,?,?,?,?,?,?)", ent_rows)
    cur.executemany("INSERT INTO x_entity_member VALUES (?,?,?,?,?)", mem_rows)

    # ---- score against ground truth ---------------------------------------
    gold = dict(conn.execute(
        "SELECT source_row_id, true_person_id FROM x_er_gold"))
    ent_of = {m["aid"]: uf.find(m["aid"]) for m in rows.values()}
    contingency = Counter()
    cluster_sizes, gold_sizes = Counter(), Counter()
    for aid, pid in gold.items():
        if aid not in ent_of:
            continue
        contingency[(ent_of[aid], pid)] += 1
        cluster_sizes[ent_of[aid]] += 1
        gold_sizes[pid] += 1

    def pairs(c):
        return c * (c - 1) // 2

    tp = sum(pairs(c) for c in contingency.values())
    cluster_pairs = sum(pairs(c) for c in cluster_sizes.values())
    gold_pairs = sum(pairs(c) for c in gold_sizes.values())
    precision = tp / cluster_pairs if cluster_pairs else 1.0
    recall = tp / gold_pairs if gold_pairs else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0

    metrics = {
        "er_precision": round(precision, 4), "er_recall": round(recall, 4),
        "er_f1": round(f1, 4), "entities": len(ent_rows),
        "accused_rows": len(rows),
        "hard_links": stats["hard:aadhaar-hash"] + stats["hard:shared-phone"],
        "fuzzy_merges": stats["fuzzy:merged"], "mo_merges": stats["mo:merged"],
        "elapsed_sec": round(time.time() - t0, 1),
    }
    for k, v in metrics.items():
        cur.execute("INSERT OR REPLACE INTO x_metric VALUES (?,?)",
                    (k, json.dumps(v)))
    conn.commit()
    return metrics
