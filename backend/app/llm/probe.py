"""Connectivity probe for the Zoho QuickML models. Run from backend/:

    ../.venv/bin/python -m app.llm.probe             # GLM text model

Prints masked token state, forces a real call, exercises the auto-refresh
path if the access token has expired, and shows the raw response shape (so we
learn the exact schema QuickML returns before wiring features to it).
"""

import json
import sys

from .zoho import CACHE_PATH, TokenError, ZohoLLM, chat_text


def mask(v: str) -> str:
    return v[:8] + "…" + v[-4:] if v and len(v) > 16 else "(unset)"


def main():
    try:
        llm = ZohoLLM()
    except TokenError as e:
        print(f"NOT READY: {e}")
        return 1
    print(f"access token : {mask(llm.access_token)}"
          f"{' (from cache)' if CACHE_PATH.exists() else ''}")
    print(f"glm endpoint : {llm.glm_url}")

    resp = llm.glm_chat(
        [{"role": "system", "content": "You are a terse test responder."},
         {"role": "user", "content": "Reply with exactly: DRISHTI-OK"}],
        max_tokens=2000)
    print("glm raw keys :", list(resp)[:8])
    print("glm response :", json.dumps(resp)[:600])
    text = chat_text(resp)
    print("glm text     :", text[:200])
    ok = "DRISHTI-OK" in (text or "")
    print("PROBE:", "PASS" if ok else "check response above")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
