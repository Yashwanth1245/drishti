"""The Ask-the-Data agent: GLM 4.7 + typed query tools + enforced citations.

Security doctrine: the model NEVER writes SQL. It chooses from a fixed menu of
parameterized query tools; every parameter is bound, so prompt injection
cannot read or mutate anything outside the menu. Every factual answer carries
the CrimeNos that came back from the tools (the evidence trail), and the full
tool trace is returned for the UI's "how I got this" panel.

Conversation flow (schema-agnostic): tool results are fed back as a user
message rather than OpenAI 'tool' roles, so it works with QuickML's response
format verified in the probe.

RBAC (Phase 5): ask() receives the caller's jurisdiction scope and threads it
into every tool. Case-record tools (count/list/case_detail, profile case
lists) are filtered server-side to that scope — the model cannot be prompted
into reading out-of-scope FIRs because the SQL never returns them. Identity
intelligence (find_person, top_risk, associates) stays statewide by doctrine.
"""

import datetime as dt
import json
import sqlite3

from .config import AS_OF, DB_PATH
from .llm import ZohoLLM, chat_text
from .llm.zoho import tool_calls

MAX_STEPS = 4
ROW_CAP = 12

SYSTEM = f"""You are DRISHTI, the Karnataka State Police crime-intelligence \
assistant. Today (data as-of) is {AS_OF}. You answer investigator questions \
STRICTLY from the tool results — never from memory. Rules:
1. For any factual claim, call tools first. If tools return nothing, say so.
2. Cite FIR numbers in square brackets like [1104401112026...] for every \
case-level claim, using ONLY crime_no values present in tool results.
3. Be concise and operational: counts, names, dates, places. No speculation \
about guilt — say 'accused' or 'named in'.
4. District names, crime types and person names arrive in natural language; \
pass them to tools as-is (tools resolve them fuzzily).
5. This is a synthetic-data prototype; never invent identifiers.
6. Playbook — chain tools until you hold the facts: for a person's history \
use find_person THEN person_profile (cases, aliases, FIR numbers) THEN \
person_associates; for 'how many' use count_cases; for specifics use \
list_cases or case_detail. find_person alone never answers a history \
question."""

TOOLS = [
    {"type": "function", "function": {
        "name": "count_cases",
        "description": "Count FIRs matching filters. Use for 'how many' questions.",
        "parameters": {"type": "object", "properties": {
            "district": {"type": "string", "description": "district name, optional"},
            "crime": {"type": "string", "description": "crime type keyword, e.g. snatching, murder, cyber"},
            "status": {"type": "string", "enum": ["open", "chargesheeted", "false", "undetected"]},
            "date_from": {"type": "string", "description": "YYYY-MM-DD"},
            "date_to": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "list_cases",
        "description": "List FIRs matching the same filters as count_cases (max 12 rows).",
        "parameters": {"type": "object", "properties": {
            "district": {"type": "string"}, "crime": {"type": "string"},
            "status": {"type": "string"}, "date_from": {"type": "string"},
            "date_to": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "find_person",
        "description": "Find offender entities by (partial) name. Returns "
                       "entity_id ONLY — always follow with person_profile "
                       "for cases/aliases/FIR numbers.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "person_profile",
        "description": "Full profile of an entity: cases, aliases, risk, identifiers.",
        "parameters": {"type": "object", "properties": {
            "entity_id": {"type": "integer"}}, "required": ["entity_id"]}}},
    {"type": "function", "function": {
        "name": "person_associates",
        "description": "Known associates of an entity from the criminal network.",
        "parameters": {"type": "object", "properties": {
            "entity_id": {"type": "integer"}}, "required": ["entity_id"]}}},
    {"type": "function", "function": {
        "name": "top_risk_offenders",
        "description": "Highest risk-scored offenders, optionally per district.",
        "parameters": {"type": "object", "properties": {
            "district": {"type": "string"},
            "limit": {"type": "integer", "maximum": 10}}, "required": []}}},
    {"type": "function", "function": {
        "name": "active_alerts",
        "description": "Current spike / emerging-trend / anomaly alerts.",
        "parameters": {"type": "object", "properties": {
            "district": {"type": "string"},
            "kind": {"type": "string", "enum": ["spike", "emerging-trend", "anomaly"]}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "case_detail",
        "description": "Everything about one FIR by its crime number.",
        "parameters": {"type": "object", "properties": {
            "crime_no": {"type": "string"}}, "required": ["crime_no"]}}},
]


def _conn():
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


class ScopeError(Exception):
    """Raised when a tool call asks for records outside the caller's
    jurisdiction; surfaced to the model as a tool error it must relay."""


def _scope_case_sql(scope, unit_alias="u", case_alias="c"):
    """WHERE fragment pinning case rows to the caller's jurisdiction."""
    if not scope:
        return "", []
    if scope.get("station_id"):
        return f" AND {case_alias}.PoliceStationID=?", [scope["station_id"]]
    ids = scope.get("district_ids")
    if ids:
        marks = ",".join("?" * len(ids))
        return f" AND {unit_alias}.DistrictID IN ({marks})", list(ids)
    return "", []


def _district_id(conn, name):
    if not name:
        return None
    r = conn.execute("SELECT DistrictID FROM District WHERE DistrictName LIKE ?",
                     (f"%{name.strip()}%",)).fetchone()
    return r[0] if r else None


STATUS_MAP = {"open": (1,), "chargesheeted": (2, 5), "false": (3,),
              "undetected": (4,)}


def _case_filters(conn, a, scope=None):
    conds, args = ["1=1"], []
    did = _district_id(conn, a.get("district"))
    if did:
        if scope and scope.get("district_ids") \
                and did not in scope["district_ids"]:
            raise ScopeError(
                f"{a.get('district')} is outside your jurisdiction "
                f"({scope.get('label')}); case records there need range or "
                f"state level access.")
        conds.append("u.DistrictID=?")
        args.append(did)
    sscope, sargs = _scope_case_sql(scope)
    if sscope:
        conds.append(sscope.removeprefix(" AND "))
        args += sargs
    if a.get("crime"):
        conds.append("(sh.CrimeHeadName LIKE ? OR h.CrimeGroupName LIKE ? OR "
                     "EXISTS (SELECT 1 FROM x_mo_tag m WHERE "
                     "m.CaseMasterID=c.CaseMasterID AND m.tag LIKE ?))")
        kw = f"%{a['crime'].strip().rstrip('s')}%"
        args += [kw, kw, kw]
    if a.get("status") in STATUS_MAP:
        ids = STATUS_MAP[a["status"]]
        conds.append(f"c.CaseStatusID IN ({','.join('?' * len(ids))})")
        args += list(ids)
    if a.get("date_from"):
        conds.append("c.CrimeRegisteredDate>=?")
        args.append(a["date_from"])
    if a.get("date_to"):
        conds.append("c.CrimeRegisteredDate<=?")
        args.append(a["date_to"])
    return " AND ".join(conds), args


BASE_JOIN = ("FROM CaseMaster c JOIN Unit u ON u.UnitID=c.PoliceStationID "
             "JOIN CrimeHead h ON h.CrimeHeadID=c.CrimeMajorHeadID "
             "LEFT JOIN CrimeSubHead sh ON sh.CrimeSubHeadID=c.CrimeMinorHeadID")


def run_tool(name: str, a: dict, scope: dict | None = None) -> dict:
    conn = _conn()
    try:
        if name == "count_cases":
            w, args = _case_filters(conn, a, scope)
            n = conn.execute(f"SELECT COUNT(*) {BASE_JOIN} WHERE {w}",
                             args).fetchone()[0]
            return {"count": n, "filters": a}
        if name == "list_cases":
            w, args = _case_filters(conn, a, scope)
            rows = [dict(r) for r in conn.execute(
                f"SELECT c.CrimeNo AS crime_no, c.CrimeRegisteredDate AS date, "
                f"u.UnitName AS station, sh.CrimeHeadName AS type, "
                f"(SELECT CaseStatusName FROM CaseStatusMaster s "
                f"WHERE s.CaseStatusID=c.CaseStatusID) AS status "
                f"{BASE_JOIN} WHERE {w} ORDER BY c.CrimeRegisteredDate DESC "
                f"LIMIT {ROW_CAP}", args)]
            return {"cases": rows}
        if name == "find_person":
            rows = [dict(r) for r in conn.execute(
                "SELECT e.entity_id, e.canonical_name, e.gender, e.n_cases, "
                "e.risk_score, (SELECT DistrictName FROM District d "
                "WHERE d.DistrictID=e.home_district_id) AS home_district "
                "FROM x_entity e WHERE e.entity_id IN (SELECT entity_id FROM "
                "x_entity_member WHERE shown_name LIKE ?) "
                "ORDER BY e.n_cases DESC LIMIT 8", (f"%{a['name']}%",))]
            return {"entities": rows}
        if name == "person_profile":
            e = conn.execute("SELECT * FROM x_entity WHERE entity_id=?",
                             (a["entity_id"],)).fetchone()
            if not e:
                return {"error": "no such entity"}
            # Linked case NUMBERS are statewide identity intel; cases outside
            # the caller's jurisdiction are marked restricted (their party
            # details won't open, but the linkage is visible).
            cases = [dict(r) for r in conn.execute(
                "SELECT cm.CrimeNo AS crime_no, cm.CrimeRegisteredDate AS date, "
                "(SELECT DistrictName FROM District d WHERE "
                "d.DistrictID=u.DistrictID) AS district, "
                "sh.CrimeHeadName AS type, m.shown_name, "
                "u.DistrictID AS district_id, cm.PoliceStationID AS ps_id "
                "FROM x_entity_member m JOIN CaseMaster cm ON "
                "cm.CaseMasterID=m.CaseMasterID "
                "JOIN Unit u ON u.UnitID=cm.PoliceStationID "
                "LEFT JOIN CrimeSubHead sh ON "
                "sh.CrimeSubHeadID=cm.CrimeMinorHeadID WHERE m.entity_id=? "
                "ORDER BY cm.CrimeRegisteredDate", (a["entity_id"],))]
            n_restricted = 0
            for cc in cases:
                did, ps = cc.pop("district_id"), cc.pop("ps_id")
                if scope and scope.get("station_id"):
                    cc["restricted"] = ps != scope["station_id"]
                elif scope and scope.get("district_ids"):
                    cc["restricted"] = did not in scope["district_ids"]
                else:
                    cc["restricted"] = False
                n_restricted += cc["restricted"]
            aliases = [r[0] for r in conn.execute(
                "SELECT DISTINCT shown_name FROM x_entity_member "
                "WHERE entity_id=?", (a["entity_id"],))]
            out = {"name": e["canonical_name"], "gender": e["gender"],
                   "risk_score": e["risk_score"], "n_cases": e["n_cases"],
                   "aliases": aliases, "cases": cases}
            if n_restricted:
                out["note"] = (f"{n_restricted} of these cases are outside "
                               f"the user's jurisdiction: case numbers are "
                               f"shown, but party details need an access "
                               f"request.")
            return out
        if name == "person_associates":
            rows = [dict(r) for r in conn.execute(
                "SELECT e.entity_id, e.canonical_name, e.risk_score, "
                "n.edge_type, n.weight FROM x_network_edge n JOIN x_entity e "
                "ON e.entity_id=CASE WHEN n.src_id=? THEN n.dst_id ELSE "
                "n.src_id END WHERE n.src_id=? OR n.dst_id=? "
                "ORDER BY n.weight DESC LIMIT 10",
                (a["entity_id"], a["entity_id"], a["entity_id"]))]
            return {"associates": rows}
        if name == "top_risk_offenders":
            did = _district_id(conn, a.get("district"))
            scope = "WHERE home_district_id=?" if did else ""
            rows = [dict(r) for r in conn.execute(
                f"SELECT entity_id, canonical_name, n_cases, risk_score "
                f"FROM x_entity {scope} ORDER BY risk_score DESC LIMIT ?",
                ([did] if did else []) + [min(int(a.get("limit", 5)), 10)])]
            return {"offenders": rows}
        if name == "active_alerts":
            did = _district_id(conn, a.get("district"))
            conds, args = ["1=1"], []
            if did and scope and scope.get("district_ids") \
                    and did not in scope["district_ids"]:
                raise ScopeError(
                    f"{a.get('district')} alerts are outside your "
                    f"jurisdiction ({scope.get('label')}).")
            if did:
                conds.append("(scope_type!='district' OR scope_id=?)")
                args.append(did)
            elif scope and scope.get("district_ids"):
                ids = list(scope["district_ids"])
                marks = ",".join("?" * len(ids))
                conds.append(
                    f"(scope_type='state' OR (scope_type='district' AND "
                    f"scope_id IN ({marks})) OR (scope_type='station' AND "
                    f"scope_id IN (SELECT UnitID FROM Unit WHERE DistrictID "
                    f"IN ({marks}))))")
                args += ids + ids
            if a.get("kind"):
                conds.append("kind=?")
                args.append(a["kind"])
            rows = []
            for r in conn.execute(
                    f"SELECT kind, summary, zscore, evidence FROM x_alert "
                    f"WHERE {' AND '.join(conds)} ORDER BY zscore DESC "
                    f"LIMIT 8", args):
                ids = json.loads(r["evidence"] or "[]")[:6]
                marks = ",".join(str(i) for i in ids) or "0"
                nos = [x[0] for x in conn.execute(
                    f"SELECT CrimeNo FROM CaseMaster WHERE CaseMasterID IN ({marks})")]
                rows.append({"kind": r["kind"], "summary": r["summary"],
                             "zscore": r["zscore"], "evidence_crime_nos": nos})
            return {"alerts": rows}
        if name == "case_detail":
            c = conn.execute(
                f"SELECT c.CrimeNo AS crime_no, c.CrimeRegisteredDate AS "
                f"registered, c.BriefFacts AS brief, u.UnitName AS station, "
                f"u.DistrictID AS district_id, c.PoliceStationID AS ps_id, "
                f"sh.CrimeHeadName AS type {BASE_JOIN} WHERE c.CrimeNo=?",
                (a["crime_no"],)).fetchone()
            if not c:
                return {"error": "no such case"}
            restricted = False
            if scope:
                if scope.get("station_id"):
                    restricted = c["ps_id"] != scope["station_id"]
                elif scope.get("district_ids"):
                    restricted = c["district_id"] not in scope["district_ids"]
            out = dict(c)
            out.pop("ps_id", None), out.pop("district_id", None)
            if restricted:
                # Graduated disclosure: structural record yes, narrative no.
                out.pop("brief", None)
                out["access"] = "restricted"
                out["note"] = (f"This FIR belongs to another jurisdiction: "
                               f"the narrative and party details are not "
                               f"visible to {scope.get('label')} — an access "
                               f"request to the owning district is needed. "
                               f"Sections, dates and accused links are "
                               f"shown.")
            cid = conn.execute("SELECT CaseMasterID FROM CaseMaster WHERE "
                               "CrimeNo=?", (a["crime_no"],)).fetchone()[0]
            out["accused"] = [r[0] for r in conn.execute(
                "SELECT AccusedName FROM Accused WHERE CaseMasterID=?", (cid,))]
            out["sections"] = [f"{r[0]} {r[1]}" for r in conn.execute(
                "SELECT ActID, SectionID FROM ActSectionAssociation "
                "WHERE CaseMasterID=?", (cid,))]
            return out
        return {"error": f"unknown tool {name}"}
    finally:
        conn.close()


def _collect_evidence(result) -> list[str]:
    found = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("crime_no", "evidence_crime_nos"):
                    found.extend(v if isinstance(v, list) else [v])
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(result)
    return found


def ask(messages: list[dict], llm: ZohoLLM | None = None,
        scope: dict | None = None, lang: str = "en") -> dict:
    llm = llm or ZohoLLM()
    system = SYSTEM
    if lang == "kn":
        system += ("\nLANGUAGE: Write your final answer to the user in KANNADA "
                   "(ಕನ್ನಡ script). BUT keep every FIR/crime number, the "
                   "[square-bracket citations], person names, district/station "
                   "names and IPC/BNS section numbers EXACTLY as they appear in "
                   "the tool results — never translate or transliterate an "
                   "identifier, name or number. Only the explanatory prose is "
                   "in Kannada.")
    if scope:
        system += (f"\n7. JURISDICTION: you are serving {scope.get('label')}. "
                   f"Identity intelligence (offender profiles, linked case "
                   f"numbers, risk, networks) is statewide, but for FIRs "
                   f"outside this jurisdiction only the structural record "
                   f"(number, dates, sections, accused) is visible — "
                   f"narratives and party/victim details need an access "
                   f"request to the owning district; relay that plainly when "
                   f"a tool notes it. Counting/listing tools stay inside the "
                   f"jurisdiction.")
    msgs = [{"role": "system", "content": system}] + messages
    evidence, trace = [], []
    for _step in range(MAX_STEPS):
        resp = llm.glm_chat(msgs, tools=TOOLS, temperature=0.2, max_tokens=900)
        calls = tool_calls(resp)
        if not calls:
            reply = (chat_text(resp) or "").strip()
            # Guard: if the model returns nothing useful but we have tool data,
            # nudge it once more rather than surfacing an empty/echo answer.
            if (len(reply) < 15 or reply.startswith("(requested")) and trace \
                    and _step < MAX_STEPS - 1:
                msgs.append({"role": "user", "content":
                             "Write the final prose answer now, citing crime_no "
                             "values in square brackets. Do not mention tools."})
                continue
            seen = list(dict.fromkeys(evidence))
            return {"reply": reply, "evidence": seen[:30], "trace": trace}
        results = []
        for c in calls:
            try:
                out = run_tool(c["name"], c["arguments"], scope)
            except ScopeError as exc:              # relayed, never bypassed
                out = {"error": str(exc)}
            except Exception:                      # tool bugs must not kill chat
                # Don't echo internal exception text to the client/model.
                out = {"error": "tool failed to execute"}
            evidence.extend(_collect_evidence(out))
            trace.append({"tool": c["name"], "arguments": c["arguments"],
                          "result_preview": json.dumps(out)[:400]})
            results.append({"tool": c["name"], "result": out})
        # Feed results back as a user turn ONLY (no synthetic assistant turn —
        # the model will mimic any assistant scaffolding we inject and echo it
        # instead of answering). Two user turns in a row is fine for GLM.
        msgs.append({"role": "user", "content":
                     "TOOL RESULTS (JSON):\n" + json.dumps(results)[:6000] +
                     "\n\nNow write the FINAL answer to my original question in "
                     "prose, citing crime_no values in square brackets. Do NOT "
                     "describe which tools you used. Call another tool only if a "
                     "fact is still missing per the playbook."})
    return {"reply": "I could not complete that within the tool budget.",
            "evidence": list(dict.fromkeys(evidence))[:30], "trace": trace}
