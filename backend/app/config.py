"""Backend configuration — every tunable threshold with its rationale.

Nothing in the engines may hardcode a weight or threshold; it lives here so a
reviewer can audit the entire analytical logic in one file.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]      # repo root
DB_PATH = ROOT / "exports" / "drishti.db"
METRICS_PATH = ROOT / "exports" / "metrics.json"

# Analytic "today": the end of the data span. Every recency/window calculation
# anchors here so demos are stable regardless of the real date.
AS_OF = "2026-06-30"

# ---------------------------------------------------------- entity resolution
# A merge needs combined evidence to clear the threshold; identical names alone
# (score ~ name+age+geo) fail for common names because of the commonness
# penalty — exactly the "two different Manjunaths" guarantee.
ER_MERGE_THRESHOLD = 0.86
ER_NAME_W = 0.62                 # token-sort ratio weight
ER_AGE_W = 0.16                  # closeness of estimated birth year
ER_GEO_SAME, ER_GEO_NEIGHBOR, ER_GEO_FAR = 0.22, 0.15, 0.04
ER_MO_BONUS = 0.08               # the two cases share an MO tag
ER_SUBHEAD_BONUS = 0.04          # same crime sub-head
ER_COMMONNESS_CAP = 0.15         # max penalty for very common name skeletons
ER_AGE_WINDOW = 3                # max |Δ birth-year estimate| to even compare
ER_MIN_NAME_RATIO = 90           # near-exact names only (variants still pass)
ER_MERGE_MAX_AGE_GAP = 2         # merge only within realistic age-drift range
# Attribute-only merges are allowed ONLY for distinctive names: if a name
# skeleton appears on more rows than this statewide, the name alone can never
# support a merge (precision-first: lakhs of people legitimately share common
# names, and the Accused table carries no father's-name/address to split them).
# Common-named repeat offenders are still caught by hard IDs and MO linkage.
ER_RARE_BLOCK_MAX = 8
ER_BLOCK_PAIR_BUDGET = 600_000   # per-block cap; beyond it tighten age window

# Pass 3 — cross-jurisdiction behavioral (MO) linkage: merges clusters that a
# conservative pass 2 left apart when name is near-identical, ages align, and
# BOTH clusters repeatedly show the same RARE modus operandi. This is the
# "repeat offender tracking across jurisdictions by MO" the challenge asks for.
ER_MO_LINK_NAME_RATIO = 92
ER_MO_LINK_MIN_EACH = 2          # rare-tag case count required on each side
ER_MO_RARE_FREQ = 0.02           # tag must appear in <2% of all cases

NEIGHBOR_DEG = 1.15              # district centroid distance => "neighboring"

# ------------------------------------------------------------------- alerts
SPIKE_WINDOW_DAYS = 90           # current window
SPIKE_BASELINE_WINDOWS = 8       # trailing windows forming the baseline
SPIKE_Z = 2.0
SPIKE_MIN_CURRENT = 4            # never alert on counts a human would ignore
EMERGING_MIN_YEAR_N = 500        # subhead volume needed for a YoY trend alert
EMERGING_GROWTH = 0.15           # +15% YoY
ANOMALY_FALSE_CASES_MIN = 3      # serial false-complainant threshold
SLOW_STATION_RATIO = 1.5         # median days-to-chargesheet vs state median
SLOW_STATION_MIN_SHEETS = 20

# ---------------------------------------------------------------------- risk
# Explainable composite, 0-100. Weights sum to 100; every factor is reported
# in risk_factors JSON so the UI can show WHY a person scores high.
RISK_W = {"frequency": 30, "recency": 25, "gravity": 25,
          "escalation": 10, "breadth": 10}
RISK_FREQ_SATURATION = 8         # cases beyond this don't add frequency score
RISK_RECENCY_HORIZON = 730       # days; older than this contributes ~0
