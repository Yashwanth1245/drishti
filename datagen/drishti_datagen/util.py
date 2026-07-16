"""Deterministic randomness and small shared helpers.

Every pipeline stage draws from its own named RNG stream derived from the master
seed, so adding or reordering stages never shifts another stage's randomness
(that property is what keeps planted stories stable across code changes).
"""

import hashlib
import random


class Rng:
    """Factory for independent, reproducible random streams."""

    def __init__(self, seed: int):
        self.seed = seed

    def stream(self, name: str) -> random.Random:
        material = f"{self.seed}:{name}".encode()
        return random.Random(int.from_bytes(hashlib.sha256(material).digest()[:8], "big"))


def weighted(rng: random.Random, pairs):
    """Pick a value from [(value, weight), ...]."""
    total = sum(w for _, w in pairs)
    x = rng.random() * total
    for value, w in pairs:
        x -= w
        if x <= 0:
            return value
    return pairs[-1][0]


def stable_offset(name: str, min_deg: float, max_deg: float):
    """Deterministic (dlat, dlon) offset for a place name — same name, same spot.

    Used to anchor taluk stations around their district HQ so the map is stable
    across regenerations without needing a real gazetteer.
    """
    h = hashlib.sha256(name.encode()).digest()
    angle = (h[0] * 256 + h[1]) / 65536 * 6.28318
    dist = min_deg + (h[2] * 256 + h[3]) / 65536 * (max_deg - min_deg)
    # cos/sin via small table-free approximation is overkill; use math
    import math
    return dist * math.cos(angle), dist * math.sin(angle)


def id_hash(value: str) -> str:
    """Salted hash of a full identity value (Aadhaar/phone as entered).

    Stored alongside the masked display value so the ER engine can hard-link
    records by exact identity WITHOUT the database ever holding the plain
    number — the same pattern real vault/tokenization systems use.
    """
    return hashlib.sha256(f"drishti:{value}".encode()).hexdigest()[:16]


class IdSeq:
    """Monotonic per-table integer ID sequences."""

    def __init__(self):
        self._counters = {}

    def next(self, table: str) -> int:
        self._counters[table] = self._counters.get(table, 0) + 1
        return self._counters[table]

    def current(self, table: str) -> int:
        return self._counters.get(table, 0)
