"""The monitoring agent's output: auto-drafted intelligence briefs.

Given a scope (district or a specific alert), gathers the live intelligence —
alerts with evidence, KPIs, top-risk entities, sample brief-facts — and asks
GLM to draft a structured brief. Every number the model sees comes from the
database; the brief's evidence list is returned alongside so the UI (and the
printed PDF) carries the trail.
"""

import json
import sqlite3

from .config import AS_OF, DB_PATH
from .llm import ZohoLLM, chat_text

SYSTEM = """You are a senior crime analyst at the Karnataka State Crime \
Records Bureau drafting an internal intelligence brief. Write in crisp \
operational English with markdown headings exactly: ## Situation, \
## Emerging patterns, ## Entities of interest, ## Recommended deployment. \
Under 350 words. Cite FIR numbers in square brackets ONLY from the data \
provided. No speculation about guilt; subjects are 'accused'. Base every \
statement on the JSON data given."""


def _conn():
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def build_brief(district_id: int | None = None, alert_id: int | None = None,
                llm: ZohoLLM | None = None) -> dict:
    conn = _conn()
    try:
        if alert_id and not district_id:
            row = conn.execute("SELECT scope_type, scope_id FROM x_alert "
                               "WHERE alert_id=?", (alert_id,)).fetchone()
            if row and row["scope_type"] == "district":
                district_id = row["scope_id"]

        dname = "Karnataka (statewide)"
        if district_id:
            dname = conn.execute("SELECT DistrictName FROM District WHERE "
                                 "DistrictID=?", (district_id,)).fetchone()[0]

        scope = "AND (scope_type!='district' OR scope_id=?)" if district_id else ""
        args = [district_id] if district_id else []
        alerts, evidence = [], []
        for r in conn.execute(
                f"SELECT alert_id, kind, summary, zscore, evidence FROM x_alert "
                f"WHERE 1=1 {scope} ORDER BY zscore DESC LIMIT 6", args):
            ids = json.loads(r["evidence"] or "[]")[:6]
            marks = ",".join(str(i) for i in ids) or "0"
            nos = [x[0] for x in conn.execute(
                f"SELECT CrimeNo FROM CaseMaster WHERE CaseMasterID IN ({marks})")]
            evidence.extend(nos)
            alerts.append({"kind": r["kind"], "summary": r["summary"],
                           "zscore": r["zscore"], "firs": nos})

        escope = "WHERE home_district_id=?" if district_id else ""
        offenders = [dict(r) for r in conn.execute(
            f"SELECT canonical_name, n_cases, risk_score FROM x_entity "
            f"{escope} ORDER BY risk_score DESC LIMIT 5", args)]

        samples = []
        if alerts and alerts[0]["firs"]:
            marks = ",".join(f"'{n}'" for n in alerts[0]["firs"][:3])
            samples = [dict(r) for r in conn.execute(
                f"SELECT CrimeNo AS crime_no, substr(BriefFacts,1,220) AS brief "
                f"FROM CaseMaster WHERE CrimeNo IN ({marks})")]

        data = {"as_of": AS_OF, "scope": dname, "alerts": alerts,
                "top_risk_offenders": offenders, "sample_cases": samples}
    finally:
        conn.close()

    llm = llm or ZohoLLM()
    resp = llm.glm_chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": "Draft the brief from this data:\n"
          + json.dumps(data)[:7000]}],
        temperature=0.3, max_tokens=900)
    return {"scope": dname, "as_of": AS_OF, "markdown": chat_text(resp),
            "evidence": list(dict.fromkeys(evidence))[:30]}
