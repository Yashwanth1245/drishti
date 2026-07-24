"""Zoho Catalyst QuickML client with automatic OAuth token refresh.

Token lifecycle: the user pastes an access token + refresh token + client
credentials into the repo-root .env. Access tokens expire (~1h); on any
401/invalid-token response this client POSTs to
{ZOHO_ACCOUNTS_BASE}/oauth/v2/token (grant_type=refresh_token), swaps in the
new access token, retries the original call once, and caches the fresh token
in .zoho_token_cache.json so restarts don't burn another refresh. The .env
file itself is never modified.

Endpoints (from the datathon's QuickML docs):
  POST {QUICKML_BASE}/project/{PROJECT}/glm/chat   — GLM 4.7, OpenAI-style
       messages + optional function tools
"""

import json
import os
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT / ".env"
CACHE_PATH = ROOT / ".zoho_token_cache.json"

REQUIRED = ["ZOHO_ACCESS_TOKEN", "ZOHO_REFRESH_TOKEN", "ZOHO_CLIENT_ID",
            "ZOHO_CLIENT_SECRET"]
PLACEHOLDER = "PASTE_"


def load_env() -> dict:
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip("'\"")
    # Container deploys (Catalyst AppSail / Docker) have no .env file —
    # process environment variables win over the file copy.
    for k, v in os.environ.items():
        if k.startswith(("ZOHO_", "QUICKML_", "CATALYST_", "DRISHTI_")) and v:
            env[k] = v
    return env


class TokenError(RuntimeError):
    """Credentials missing/invalid — the caller maps this to a 503 asking for
    configuration."""
    pass


class LLMError(RuntimeError):
    """The QuickML upstream failed (non-200, timeout, transport error). The
    caller maps this to a 503 'AI temporarily unavailable' rather than a 500."""
    pass


class ZohoLLM:
    def __init__(self):
        self.env = load_env()
        missing = [k for k in REQUIRED
                   if not self.env.get(k) or self.env[k].startswith(PLACEHOLDER)]
        if missing:
            raise TokenError(
                f"Fill these in {ENV_PATH}: {', '.join(missing)}")
        self.access_token = self.env["ZOHO_ACCESS_TOKEN"]
        # a cached refreshed token is fresher than the pasted one
        if CACHE_PATH.exists():
            try:
                cache = json.loads(CACHE_PATH.read_text())
                if cache.get("expires_at", 0) > time.time() + 60:
                    self.access_token = cache["access_token"]
            except (json.JSONDecodeError, KeyError):
                pass
        base = self.env.get("QUICKML_BASE",
                            "https://api.catalyst.zoho.in/quickml/v1")
        project = self.env["QUICKML_PROJECT_ID"]
        self.glm_url = f"{base}/project/{project}/glm/chat"
        self.client = httpx.Client(timeout=120)

    # ---- auth ------------------------------------------------------------
    def _headers(self):
        return {"Content-Type": "application/json",
                "Authorization": f"Bearer {self.access_token}",
                "CATALYST-ORG": self.env["CATALYST_ORG"]}

    def refresh(self) -> str:
        """Exchange the refresh token for a new access token; cache it."""
        r = self.client.post(
            f"{self.env.get('ZOHO_ACCOUNTS_BASE', 'https://accounts.zoho.in')}"
            f"/oauth/v2/token",
            params={
                "refresh_token": self.env["ZOHO_REFRESH_TOKEN"],
                "client_id": self.env["ZOHO_CLIENT_ID"],
                "client_secret": self.env["ZOHO_CLIENT_SECRET"],
                "redirect_uri": self.env.get("ZOHO_REDIRECT_URI",
                                             "https://www.zoho.com/catalyst"),
                "grant_type": "refresh_token",
            })
        body = r.json()
        if "access_token" not in body:
            raise TokenError(f"Token refresh failed: {body}")
        self.access_token = body["access_token"]
        CACHE_PATH.write_text(json.dumps({
            "access_token": self.access_token,
            "expires_at": time.time() + int(body.get("expires_in", 3600)),
        }))
        return self.access_token

    @staticmethod
    def _token_rejected(r: httpx.Response) -> bool:
        if r.status_code in (401, 403):
            return True
        try:
            text = json.dumps(r.json()).lower()
        except (json.JSONDecodeError, ValueError):
            text = r.text.lower()
        return "invalid_token" in text or "invalid oauth" in text \
            or "oauth_token" in text and "invalid" in text

    def _post(self, url: str, payload: dict) -> dict:
        try:
            r = self.client.post(url, json=payload, headers=self._headers())
            if self._token_rejected(r):
                self.refresh()                      # one retry on expiry
                r = self.client.post(url, json=payload, headers=self._headers())
        except httpx.HTTPError as e:                # timeout / connection reset
            raise LLMError(f"QuickML request failed: {e}") from e
        if r.status_code != 200:
            raise LLMError(f"QuickML {r.status_code}: {r.text[:800]}")
        return r.json()

    # ---- models ------------------------------------------------------------
    def glm_chat(self, messages: list[dict], tools: list[dict] | None = None,
                 temperature: float = 0.4, max_tokens: int = 900,
                 thinking: bool = False) -> dict:
        payload = {
            "model": self.env.get("GLM_MODEL", "crm-di-glm47b_30b_it"),
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": thinking},
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return self._post(self.glm_url, payload)


def chat_text(resp: dict) -> str:
    """Extract assistant text. QuickML GLM returns {"response": "...",
    "tool_calls": [...], "usage": ...} (verified live 2026-07-02); OpenAI-style
    kept as fallback."""
    if isinstance(resp, dict):
        if isinstance(resp.get("response"), str):
            return resp["response"]
        choices = resp.get("choices")
        if choices:
            msg = choices[0].get("message", {})
            return msg.get("content") or msg.get("reasoning_content") or ""
        for key in ("output", "text", "content", "result"):
            if isinstance(resp.get(key), str):
                return resp[key]
    return json.dumps(resp)[:2000]


def tool_calls(resp: dict) -> list[dict]:
    """Extract tool calls: QuickML puts them top-level; normalize each to
    {"name": str, "arguments": dict}."""
    raw = resp.get("tool_calls") or []
    if not raw:
        try:
            raw = resp["choices"][0]["message"].get("tool_calls") or []
        except (KeyError, IndexError, TypeError):
            raw = []
    out = []
    for c in raw:
        fn = c.get("function", c)
        name = fn.get("name")
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if name:
            out.append({"name": name, "arguments": args})
    return out
