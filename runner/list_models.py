"""List which Claude models this API key can use.

Run by the job watcher as a runner job, which puts the key in this process
only. Never prints the key. Free calls only (the Models API), unless --probe
is given: then it sends one tiny message to each Mythos id to confirm the
organization is cleared to call it (a few cents in total).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.anthropic.com/v1"
VERSION = "2026-10-21"
TARGETS = [
    "claude-haiku-5-5",
    "claude-sonnet-5-5",
    "claude-opus-5-5",
    "claude-fable-5-2",
    "claude-mythos-5-2",
    "claude-mythos-5-1",
]
PROBE = ["claude-mythos-5-2", "claude-mythos-5-1"]


def call(method: str, path: str, key: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("x-api-key", key)
    req.add_header("anthropic-version", VERSION)
    if data is not None:
        req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def err(payload: dict) -> str:
    e = payload.get("error") or {}
    return f"{e.get('type', '?')}: {str(e.get('message', ''))[:160]}"


def main() -> int:
    if os.environ.get("STAKES_ALLOW_API") != "yes":
        print("STAKES_ALLOW_API is not yes. Run this through the job watcher. No request made.")
        return 2
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("No API key in this process. No request made.")
        return 2

    print("[1/3] Listing models...", flush=True)
    ids: list[str] = []
    after = None
    while True:
        path = "/models?limit=1000" + (f"&after_id={after}" if after else "")
        status, page = call("GET", path, key)
        if status != 200:
            print(f"List failed, HTTP {status}, {err(page)}")
            return 1
        ids += [m["id"] for m in page.get("data", [])]
        if not page.get("has_more"):
            break
        after = page.get("last_id")
    print(f"  {len(ids)} ids listed")
    fm = sorted(i for i in ids if "fable" in i or "mythos" in i)
    print("  Fable and Mythos ids listed: " + (", ".join(fm) if fm else "none"))

    print("[2/3] Checking each study model...", flush=True)
    for mid in TARGETS:
        status, m = call("GET", f"/models/{mid}", key)
        if status == 200:
            eff = m.get("capabilities", {}).get("effort", {}).get("low", {}).get("supported")
            print(f"  {mid}: HTTP 200, listed={mid in ids}, effort low supported={eff}")
        else:
            print(f"  {mid}: HTTP {status}, {err(m)}")

    if "--probe" in sys.argv[1:]:
        print("[3/3] One tiny message to each Mythos id...", flush=True)
        for mid in PROBE:
            body = {
                "model": mid,
                "max_tokens": 256,
                "output_config": {"effort": "low"},
                "messages": [{"role": "user", "content": "Reply with the word ok."}],
            }
            status, r = call("POST", "/messages", key, body)
            if status == 200:
                u = r.get("usage", {})
                print(f"  {mid}: CALLABLE, HTTP 200, stop={r.get('stop_reason')}, "
                      f"in={u.get('input_tokens')} out={u.get('output_tokens')}")
            else:
                print(f"  {mid}: NOT CALLABLE, HTTP {status}, {err(r)}")
    else:
        print("[3/3] Skipped the message probe (no --probe).")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
