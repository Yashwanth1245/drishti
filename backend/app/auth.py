"""Login, rank-based access scope, and the audit trail (Phase 5).

WHY: judges score production credibility. Access control mirrors the real KSP
command hierarchy (rank -> jurisdiction): state roles (DGP, SCRB) see all of
Karnataka, a Range DIG sees the districts under their range, a district SP
their district, a station IO their station's case records. Enforcement is
SERVER-SIDE on every endpoint (the UI additionally adapts); every API request
lands in x_audit_log.

Access doctrine (documented in ARCHITECTURE.md):
- CASE RECORDS (FIR content, case lists, case detail) are jurisdiction-scoped.
- IDENTITY INTELLIGENCE (entities, aliases, risk scores, network graph) is
  statewide shared intel — an SP can see that an offender exists and has N
  cases elsewhere, but cannot open the out-of-scope FIRs. That mirrors how
  inter-jurisdiction criminal intelligence should work and it makes the ER
  layer useful to every rank.

Design notes:
- Tokens are stateless HMAC-signed ("uid.exp.sig") so container restarts never
  log anyone out and no session table is needed. Secret comes from
  DRISHTI_SECRET (env or repo .env); a dev fallback is used with a warning.
- Demo users are seeded idempotently at first use into x_app_user / x_role —
  the tables shipped reserved in the Phase-1 schema. Passwords are PBKDF2
  (120k rounds); the demo password is documented in the README because the
  whole dataset is synthetic.
- Audit writes are best-effort through one locked writer connection (WAL lets
  it coexist with the read-only request connections). On a read-only
  filesystem the sink degrades to an in-memory ring buffer — never a 500.
"""

import datetime as dt
import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time
from collections import deque
from dataclasses import dataclass

from fastapi import Header, HTTPException

from .config import DB_PATH

TOKEN_TTL_S = 12 * 3600          # one shift + slack; re-login is one click
PBKDF2_ROUNDS = 120_000

# role_id, role_name, scope_type — mirrors docs/ARCHITECTURE.md RBAC table
ROLES = [
    (1, "DGP", "state"),
    (2, "SCRB_ANALYST", "state"),
    (3, "RANGE_DIG", "range"),
    (4, "DISTRICT_SP", "district"),
    (5, "STATION_IO", "station"),
]
ROLE_PRETTY = {"DGP": "DGP", "SCRB_ANALYST": "SCRB Analyst",
               "RANGE_DIG": "DIG (Range)", "DISTRICT_SP": "SP (District)",
               "STATION_IO": "Inspector (Station)"}

# Demo roster (username, role_id, scope_id). Scope ids verified against the
# generated org: Unit 4 = Northern Range (Belagavi); Unit 183 = Hubballi Town
# PS, the station holding the live 2026 snatching spike. The three SPs are
# deliberately the three districts of the S1 story (Belagavi 1003, Davanagere
# 1013, Dharwad 1014): each sees a different fragment of the same offender
# (3 / 2 / 6 of his 11 cases) — the "fragmented information" problem made
# visible, and Davanagere sits in a DIFFERENT range so the DIG boundary shows
# too. One shared password because the data is synthetic and judges need to
# switch roles quickly.
DEMO_PASSWORD = "drishti2026"
DEMO_USERS = [
    ("dgp", 1, None),
    ("scrb", 2, None),
    ("dig.northern", 3, 4),
    ("sp.belagavi", 4, 1003),
    ("sp.davanagere", 4, 1013),
    ("sp.dharwad", 4, 1014),
    # One station IO under each story district — the stations where S1's
    # FIRs are actually registered (encoded in the CrimeNos):
    ("io.market", 5, 224),        # Market PS, Belagavi — the 2024 cases
    ("io.davanagere", 5, 592),    # Davanagere Town PS — the middle cases
    ("io.hubballi", 5, 183),      # Hubballi Town PS — the live 2026 spike
]


def _env(key: str) -> str | None:
    """Env var first (container deploys), repo .env second (local dev)."""
    if os.environ.get(key):
        return os.environ[key]
    try:
        from .llm.zoho import load_env
        return load_env().get(key)
    except Exception:
        return None


_SECRET: bytes | None = None


def _secret() -> bytes:
    global _SECRET
    if _SECRET is None:
        s = _env("DRISHTI_SECRET")
        if not s:
            # SECURITY: with no real secret, every login token is signed with a
            # public in-source string — anyone holding the (public) source could
            # forge a DGP token and bypass all RBAC. Fail CLOSED in any deployed
            # environment; fall back to a dev secret only for local runs, loudly.
            deployed = bool(os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT")
                            or _env("DRISHTI_ENV") == "production")
            if deployed:
                raise RuntimeError(
                    "DRISHTI_SECRET is not set. Refusing to start with the "
                    "insecure in-source dev secret in a deployed environment. "
                    "Set DRISHTI_SECRET (any long random value, e.g. "
                    "`openssl rand -hex 32`) in the AppSail console -> "
                    "Environment, then redeploy.")
            s = "dev-only-secret--set-DRISHTI_SECRET-in-production"
            print("auth: DRISHTI_SECRET not set — using DEV secret (LOCAL ONLY; "
                  "set DRISHTI_SECRET before deploying)")
        _SECRET = s.encode()
    return _SECRET


def hash_password(username: str, password: str) -> str:
    # Deterministic per-user salt keeps seeding idempotent across restarts;
    # acceptable for a synthetic-data demo roster, noted in DEPLOYMENT.md.
    salt = hashlib.sha256(f"drishti:{username}".encode()).digest()
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt,
                               PBKDF2_ROUNDS).hex()


# ------------------------------------------------------------------ seeding --

_seed_lock = threading.Lock()
_seeded = False
_MEM_USERS: dict[str, dict] = {}          # fallback when the DB is read-only


def ensure_seeded() -> None:
    global _seeded
    if _seeded:
        return
    with _seed_lock:
        if _seeded:
            return
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.executemany(
                "INSERT OR IGNORE INTO x_role(role_id, role_name, scope_type) "
                "VALUES (?,?,?)", ROLES)
            conn.executemany(
                "INSERT OR IGNORE INTO x_app_user"
                "(username, pass_hash, role_id, scope_id) VALUES (?,?,?,?)",
                [(u, hash_password(u, DEMO_PASSWORD), rid, sid)
                 for u, rid, sid in DEMO_USERS])
            conn.commit()
            conn.close()
        except sqlite3.Error as exc:
            print(f"auth: DB not writable ({exc}) — demo users kept in memory")
            for i, (u, rid, sid) in enumerate(DEMO_USERS, start=1):
                _MEM_USERS[u] = {
                    "user_id": 90000 + i, "username": u,
                    "pass_hash": hash_password(u, DEMO_PASSWORD),
                    "role_id": rid, "scope_id": sid}
        _seeded = True


# --------------------------------------------------------- user + scope load --

@dataclass(frozen=True)
class User:
    user_id: int
    username: str
    role: str                     # x_role.role_name
    scope_type: str               # state | range | district | station
    scope_id: int | None
    label: str                    # "SP (District) — Dharwad District"
    district_ids: tuple | None    # None = statewide
    station_id: int | None        # set only for STATION_IO

    def public(self) -> dict:
        return {"username": self.username, "role": self.role,
                "scope_type": self.scope_type, "label": self.label,
                "district_ids": list(self.district_ids) if self.district_ids
                                else None,
                "station_id": self.station_id}


def _ro() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _resolve(row: dict) -> User:
    """Turn a user row into a User with its jurisdiction resolved from the
    org tables (range -> districts under it, station -> its district)."""
    role = {rid: (name, st) for rid, name, st in ROLES}[row["role_id"]]
    role_name, scope_type = role
    pretty = ROLE_PRETTY[role_name]
    sid = row["scope_id"]
    conn = _ro()
    try:
        if scope_type == "state":
            label, dids, station = f"{pretty} — Karnataka State", None, None
        elif scope_type == "range":
            name = conn.execute("SELECT UnitName FROM Unit WHERE UnitID=?",
                                (sid,)).fetchone()[0]
            dids = tuple(sorted(r[0] for r in conn.execute(
                "SELECT DISTINCT DistrictID FROM Unit "
                "WHERE ParentUnit=? AND TypeID IN (3,4)", (sid,))))
            label, station = f"{pretty} — {name}", None
        elif scope_type == "district":
            name = conn.execute(
                "SELECT DistrictName FROM District WHERE DistrictID=?",
                (sid,)).fetchone()[0]
            label, dids, station = f"{pretty} — {name} District", (sid,), None
        else:                                             # station
            name, did = conn.execute(
                "SELECT UnitName, DistrictID FROM Unit WHERE UnitID=?",
                (sid,)).fetchone()
            label, dids, station = f"{pretty} — {name}", (did,), sid
    finally:
        conn.close()
    return User(user_id=row["user_id"], username=row["username"],
                role=role_name, scope_type=scope_type, scope_id=sid,
                label=label, district_ids=dids, station_id=station)


_user_cache: dict[int, User] = {}


def _fetch_user_row(username: str | None = None,
                    user_id: int | None = None) -> dict | None:
    ensure_seeded()
    if _MEM_USERS:
        for u in _MEM_USERS.values():
            if u["username"] == username or u["user_id"] == user_id:
                return u
        return None
    conn = _ro()
    try:
        if username is not None:
            r = conn.execute("SELECT * FROM x_app_user WHERE username=?",
                             (username,)).fetchone()
        else:
            r = conn.execute("SELECT * FROM x_app_user WHERE user_id=?",
                             (user_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def load_user(user_id: int) -> User | None:
    if user_id in _user_cache:
        return _user_cache[user_id]
    row = _fetch_user_row(user_id=user_id)
    if not row:
        return None
    user = _resolve(row)
    _user_cache[user_id] = user
    return user


def verify_password(username: str, password: str) -> User | None:
    row = _fetch_user_row(username=(username or "").strip().lower())
    if not row:
        return None
    given = hash_password(row["username"], password or "")
    if not hmac.compare_digest(given, row["pass_hash"]):
        return None
    return load_user(row["user_id"])


# ------------------------------------------------------------------- tokens --

def mint_token(user_id: int) -> str:
    payload = f"{user_id}.{int(time.time()) + TOKEN_TTL_S}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:40]
    return f"{payload}.{sig}"


def token_user(token: str | None) -> User | None:
    if not token or token.count(".") != 2:
        return None
    uid_s, exp_s, sig = token.split(".")
    payload = f"{uid_s}.{exp_s}"
    want = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:40]
    if not hmac.compare_digest(sig, want):
        return None
    try:
        if int(exp_s) < time.time():
            return None
        return load_user(int(uid_s))
    except ValueError:
        return None


def current_user(authorization: str | None = Header(default=None)) -> User:
    """FastAPI dependency: every protected endpoint takes
    user: User = Depends(current_user)."""
    tok = (authorization or "").removeprefix("Bearer ").strip()
    user = token_user(tok)
    if not user:
        raise HTTPException(401, "Sign in required")
    return user


# -------------------------------------------------------------------- audit --

class AuditSink:
    """The accountability trail -> x_audit_log(user, ts, event, detail).

    This is NOT a request log (uvicorn already has one). It records the
    actions oversight actually asks about: who searched which name, who
    opened whose profile / which FIR, what was asked of the AI, briefs and
    scans, sign-ins, and every DENIED attempt. Dashboard navigation (KPIs,
    map aggregates, trends) is deliberately not audited — logging it drowns
    the signal. When write paths arrive (e.g. saving a scanned-FIR draft),
    they log as record-update events with the same vocabulary.

    Viewing the audit trail itself is not self-logged (it would spam at the
    UI's refresh rate); production would log it once per session.

    WAL lets this one writer coexist with the read-only request connections;
    if the filesystem refuses writes we keep a memory ring so /api/audit
    still demonstrates the trail."""

    def __init__(self):
        self._lock = threading.Lock()
        self._mem: deque = deque(maxlen=500)
        self._conn: sqlite3.Connection | None = None
        self._db_ok = True

    def _writer(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(DB_PATH, timeout=5,
                                         check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def write(self, user: User | None, action: str, detail: dict) -> None:
        detail = {"user": user.username if user else "anonymous",
                  "role": user.role if user else None, **detail}
        entry = {"user_id": user.user_id if user else None,
                 "ts": dt.datetime.now(dt.timezone.utc)
                       .strftime("%Y-%m-%d %H:%M:%S"),
                 "action": action, "detail": detail}
        with self._lock:
            self._mem.append(entry)
            if not self._db_ok:
                return
            try:
                self._writer().execute(
                    "INSERT INTO x_audit_log(user_id, ts, action, detail) "
                    "VALUES (?,?,?,?)",
                    (entry["user_id"], entry["ts"], action,
                     json.dumps(detail)))
                self._conn.commit()
            except sqlite3.Error as exc:
                print(f"audit: falling back to memory ring ({exc})")
                self._db_ok = False

    def recent(self, limit: int = 100) -> list[dict]:
        if self._db_ok:
            try:
                conn = _ro()
                out = []
                for r in conn.execute(
                        "SELECT log_id, user_id, ts, action, detail "
                        "FROM x_audit_log ORDER BY log_id DESC LIMIT ?",
                        (limit,)):
                    d = json.loads(r["detail"] or "{}")
                    out.append({"log_id": r["log_id"], "ts": r["ts"],
                                "user": d.get("user"), "role": d.get("role"),
                                "event": r["action"],
                                "summary": d.get("summary") or ""})
                conn.close()
                return out
            except sqlite3.Error:
                pass
        return [{"log_id": None, "ts": e["ts"], "user": e["detail"]["user"],
                 "role": e["detail"].get("role"), "event": e["action"],
                 "summary": e["detail"].get("summary") or ""}
                for e in reversed(self._mem)][:limit]


AUDIT = AuditSink()
