"""Clawlings viewer: replay finished episodes or watch running ones live.

    python -m viewer.server                      # logs from runs_dir in runner/config.json
    python -m viewer.server --runs D:\\some\\runs --port 8765
    python -m viewer.server --demo               # play the demo logs from viewer/make_demo.py

Then open http://127.0.0.1:8765 in a browser. The server listens on this
machine only, reads episode logs (*.jsonl.gz) and spend ledgers under the runs
folder, and never writes anything. Blinded confirmatory logs are stripped of
condition and check-in information before they leave this process
(viewer/logread.py). --show-blinded lifts that, for after the primary test.

Needs only the standard library plus the world package (numpy, gymnasium) for
the map replay. The runner never imports this, and runs the same without it.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from viewer.logread import episode_summary, episode_view, phase_spend  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
DEMO_RUNS = Path(__file__).resolve().parent / "_demo_runs"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png"}


def load_config() -> dict:
    try:
        return json.loads((ROOT / "runner" / "config.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def list_episodes(runs: Path, opts: dict) -> list[dict]:
    items = []
    if runs.is_dir():
        for p in runs.rglob("*.jsonl.gz"):
            try:
                items.append(episode_summary(p, p.relative_to(runs).as_posix(), **opts))
            except Exception:
                continue
    items.sort(key=lambda e: e["mtime"], reverse=True)
    return items


class Handler(BaseHTTPRequestHandler):
    runs: Path = Path(".")
    opts: dict = {}
    caps: dict = {}

    def log_message(self, fmt, *args):
        pass  # the heartbeat thread prints status instead of one line per request

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _log_path(self, rel: str) -> Path | None:
        """Resolve a relative log path, refusing anything outside the runs folder."""
        if not rel or not rel.endswith(".jsonl.gz"):
            return None
        runs = self.runs.resolve()
        p = (runs / rel).resolve()
        if runs not in p.parents or not p.is_file():
            return None
        return p

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/api/episodes":
            return self._json({"runs_dir": str(self.runs), "episodes": list_episodes(self.runs, self.opts)[:500],
                               "spend": phase_spend(self.runs, self.caps), "now": time.time()})
        if u.path == "/api/episode":
            rel = (q.get("path") or [""])[0]
            p = self._log_path(rel)
            if p is None:
                return self._json({"error": "no such episode log"}, 404)
            try:
                return self._json(episode_view(p, rel, **self.opts))
            except Exception as e:
                return self._json({"error": f"could not read the log: {type(e).__name__}"}, 500)
        name = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
        f = (STATIC / name).resolve()
        if STATIC.resolve() not in f.parents or not f.is_file():
            return self._send(404, b"not found", "text/plain")
        return self._send(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))


def heartbeat(runs: Path, opts: dict, every: float):
    """A status line now and then, so the window never looks frozen."""
    while True:
        eps = list_episodes(runs, opts)
        live = [e for e in eps if e["running"]]
        now = time.strftime("%H:%M:%S")
        if live:
            e = live[0]
            print(f"[{now}] {len(eps)} episodes, {len(live)} running. Newest live: {e['path']} at turn {e['turns']}", flush=True)
        else:
            print(f"[{now}] {len(eps)} episodes, none running. Waiting for the runner...", flush=True)
        time.sleep(every)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Clawlings episode viewer")
    ap.add_argument("--runs", type=Path, default=None, help="folder holding episode logs (default: runs_dir in runner/config.json)")
    ap.add_argument("--demo", action="store_true", help="read viewer/_demo_runs (made by viewer/make_demo.py)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--show-blinded", action="store_true",
                    help="show condition and check-in data in blinded confirmatory logs; only after the primary test has run")
    ap.add_argument("--stall-minutes", type=float, default=10.0,
                    help="a log with no end line that hasn't changed for this long counts as a stopped run, not a live one")
    ap.add_argument("--heartbeat", type=float, default=30.0, help="seconds between status lines")
    a = ap.parse_args(argv)
    cfg = load_config()
    runs = DEMO_RUNS if a.demo else (a.runs or Path(cfg.get("runs_dir") or ROOT / "runs"))
    Handler.runs = runs
    Handler.opts = {"blinded_phases": tuple(cfg.get("blinded_phases") or ("confirmatory",)), "show_blinded": a.show_blinded,
                     "stall_after": a.stall_minutes * 60}
    Handler.caps = cfg.get("caps_usd") or {}
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"Clawlings viewer: open http://127.0.0.1:{a.port}", flush=True)
    print(f"Reading logs from {runs}" + ("  (blinded logs SHOWN IN FULL)" if a.show_blinded else ""), flush=True)
    print("Ctrl+C stops it.", flush=True)
    threading.Thread(target=heartbeat, args=(runs, Handler.opts, a.heartbeat), daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
