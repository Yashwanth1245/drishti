"""Loads the curated real-world reference JSONs and unifies district naming.

The four files in reference/ come from independent research passes, so the same
district can appear as "Bagalkote", "Bagalkote (Bagalkot)" or
"Ramanagara (renamed Bengaluru South, 2024)". This module is the ONLY place that
normalization logic lives; every stage receives one merged district list.
"""

import json

from .config import REFERENCE_DIR, DISTRICT_HQ_COORDS

# demographics-file base name -> police-file base name
ALIASES = {"Ramanagara": "Bengaluru South"}


def _base(name: str) -> str:
    b = name.split(" (")[0].strip()
    return ALIASES.get(b, b)


def load():
    """Return dict(police=..., legal=..., demo=..., stats=..., districts=[merged])."""
    police = json.loads((REFERENCE_DIR / "police_structure.json").read_text())
    legal = json.loads((REFERENCE_DIR / "legal_sections.json").read_text())
    demo = json.loads((REFERENCE_DIR / "demographics_names.json").read_text())
    stats = json.loads((REFERENCE_DIR / "crime_calibration.json").read_text())

    demo_by_name = {_base(d["name"]): d for d in demo["districts"]}
    districts = []
    for pd in police["districts"]:
        name = _base(pd["name"])
        dd = demo_by_name.get(name)
        if dd is None:
            raise ValueError(f"district {name!r} missing from demographics reference")
        if name not in DISTRICT_HQ_COORDS:
            raise ValueError(f"district {name!r} missing HQ coordinates in config")
        districts.append({
            "name": name,
            "hq": pd.get("hq") or name,
            "policing": pd.get("policing", ""),
            "taluks": pd.get("taluks") or [name],
            "pop2011": dd.get("pop2011") or 1_500_000,
            "popEstimate": dd.get("popEstimate") or dd.get("pop2011") or 1_500_000,
            "urbanPct": dd.get("urbanPct") or 25.0,
            "literacyPct": dd.get("literacyPct") or 68.0,  # Vijayanagara unverified — fallback
            "sexRatio": dd.get("sexRatio") or 975,
            "hq_coords": DISTRICT_HQ_COORDS[name],
        })
    if len(districts) != 31:
        raise ValueError(f"expected 31 districts, got {len(districts)}")

    return {"police": police, "legal": legal, "demo": demo, "stats": stats,
            "districts": districts}
