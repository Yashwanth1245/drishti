"""DRISHTI synthetic data generator.

Produces the full Karnataka crime database (KSP FIR schema + DRISHTI extensions)
from curated real-world reference data in ../reference/. Fully deterministic:
same --seed => byte-identical output. See docs/SYNTHETIC_DATA_DESIGN.md for the
specification and docs/STATUS.md for which pipeline stages are implemented.
"""

__version__ = "0.1.0"
