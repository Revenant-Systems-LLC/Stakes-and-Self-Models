"""Run twin pairs for Arm 1 under hard spending caps.

    python -m runner.run --phase dev --client fake
    python -m runner.run --phase pilot --client claude --key-expires 2026-12-03T21:35-06:00
        (the claude client needs STAKES_ALLOW_API=yes, set by the job watcher)

For each world seed the stakes twin runs first, then the no-stakes twin with
max_turns set to the turn its stakes twin ended. Pair order across tiers is
shuffled by a fixed seed (the tiers phase alternates instead). An episode that
crashes or fails at the API past its retries is excluded; its seed is replaced
by the tier's next seed and both twins rerun on it. Refusals and bad replies
are logged and counted, never dropped.

The API key. If the API refuses it (HTTP 401 or authentication_error), or says it
cannot use the model (HTTP 403 permission_error, 404 not_found_error), the whole
run stops at once: no retry, no exclusion, no other model tried in its place, the
episode's log is closed as incomplete (incomplete_auth or stopped_access). Rerunning the same phase resumes: finished episodes are skipped and
the incomplete one is played again on the same seed, into a new log file.
--key-expires (ISO 8601 with an offset) is required for every phase except dev.
Before each pair the runner stops cleanly if the key would expire before the
pair and its margin were over, so no batch straddles an expiry. The key itself
is never read, printed or logged here.

A status line prints at least every 30 seconds while a run is going.

Caps, priors, models and paths live in the config file. There is no command-line
option that changes a cap, a path or the ledger. Exit codes: 0 plan finished,
2 refused to start, 3 stopped by the spend cap, 4 stopped by another guard,
5 stopped because the key was refused, cannot use the model, or is about to expire.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tqdm import tqdm

from runner import gate, plan
from runner.claude_critter import ClaudeCritter
from runner.config import ALL_TIERS, PHASES, REAL_PHASES, Config, ConfigError, load_config, read_text_file
from runner.fake_client import FakeClient, random_valid_script
from runner.ledger import Ledger, LedgerError, PriceError, PriceTable
from runner.play import play_episode
from runner.plan import RunnerError
from world import blinding
from world.env import CONDITIONS
from world.log import code_version

AUTH_LINE = "The API key was refused (it may have expired). Put a new key in the vault and run the job again."
ACCESS_LINE = ("The API says this key cannot use the model, or the model does not exist (HTTP 403 or 404). The run "
               "stopped. No other model was tried. Check the model name and the key's access, then run the job again.")
DEFAULT_PAIR_ESTIMATE = timedelta(minutes=30)   # the key-expiry guard's guess until a pair has finished in this run
EXPIRY_MARGIN = timedelta(hours=1)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fmt_time(dt: datetime) -> str:
    return dt.isoformat(timespec="minutes" if dt.second == 0 and dt.microsecond == 0 else "seconds")


def parse_key_expires(text: str) -> datetime:
    """An ISO 8601 time with an offset, such as 2026-12-03T21:35-06:00."""
    try:
        dt = datetime.fromisoformat(text.strip())
    except ValueError:
        dt = None
    if dt is None or dt.tzinfo is None or dt.utcoffset() is None:
        raise RunnerError(f"--key-expires must be an ISO 8601 time with an offset, such as 2026-12-03T21:35-06:00; got {text!r}")
    return dt


def require_key_expires(phase: str, key_expires) -> None:
    if phase != "dev" and key_expires is None:
        raise RunnerError(f"--key-expires is required for the {phase} phase (every phase except dev). The Clawlings key is "
                          f"replaced every 7 days; give the time this one expires, such as --key-expires 2026-12-03T21:35-06:00")


class Heartbeat:
    """A status line at least every `interval` seconds, so a run in a log window never looks frozen. The main thread
    keeps the state current (update) and a background thread prints it (beat), so a slow API call cannot hide it.
    The thread only formats and prints what the main thread stored; it never reads the ledger itself."""

    def __init__(self, say, interval: float = 30.0, clock=time.monotonic):
        self.say, self.interval, self.clock = say, float(interval), clock
        self._lock = threading.Lock()
        self._state: dict = {}
        self._last = clock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def update(self, **fields):
        with self._lock:
            self._state.update(fields)

    def beat(self, force: bool = False) -> bool:
        """Print the status line if `interval` has passed since the last one (or force). Returns whether it printed."""
        with self._lock:
            now = self.clock()
            if (not force and now - self._last < self.interval) or not self._state:
                return False
            st = dict(self._state)
            self._last = now
        self.say(self.line(st))
        return True

    @staticmethod
    def line(st: dict) -> str:
        spend, cap = st.get("spend", 0.0), st.get("cap", 0.0)
        pct = f" ({100 * spend / cap:.0f}%)" if cap else ""
        return (f"heartbeat {datetime.now().strftime('%H:%M:%S')} | phase {st.get('phase')} | model {st.get('model', '-')} | "
                f"pair {st.get('pair', '-')}/{st.get('pairs', '-')} | turn {st.get('turn', '-')}/{st.get('max_turns', '-')} | "
                f"spend ${spend:.2f} of ${cap:.2f} cap{pct}")

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="heartbeat", daemon=True)
            self._thread.start()

    def _loop(self):
        while not self._stop.wait(min(1.0, self.interval / 2)):
            self.beat()

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)


class Manifest:
    """Append-only record of every episode outcome and exclusion for one phase. The runner resumes from it.
    It holds outcomes, so it is the runner's own file: the dashboard reads the ledger and logs, not this."""

    def __init__(self, path: Path):
        self.path = path
        self.records: list[dict] = []
        if path.exists():
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                try:
                    self.records.append(json.loads(line))
                except ValueError as e:
                    raise RunnerError(f"{path} line {n} is not valid JSON ({e}); fix it by hand") from e

    def append(self, obj: dict):
        obj = {"time": _now(), **obj}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.records.append(obj)

    def attempts(self, tier: str, seed: int, label: str) -> int:
        """Episodes already logged for this twin. Above 0 only after a stop (key refused, cap): the redo gets its own file."""
        return sum(1 for r in self.records if r.get("type") == "episode" and r["tier"] == tier and r["seed"] == seed
                   and r["condition_code"] == label)

    def done(self, tier: str, seed: int, label: str) -> dict | None:
        for r in reversed(self.records):
            if (r.get("type") == "episode" and r["status"] == "done" and r["tier"] == tier and r["seed"] == seed
                    and r["condition_code"] == label):
                return r
        return None

    def excluded_seeds(self, tier: str) -> set[int]:
        return {r["seed"] for r in self.records if r.get("type") == "pair_excluded" and r["tier"] == tier}

    def logged_paths(self) -> set[str]:
        return {r["log_path"] for r in self.records if r.get("type") == "episode"}


@dataclass
class RunReport:
    phase: str
    stop: str | None = None          # None (finished) | "cap" | "seed_list" | "exclusions" | "auth" | "access" | "key_expiry"
    pairs_done: int = 0
    episodes_run: int = 0
    exclusions: list = field(default_factory=list)
    spend: float = 0.0
    cap: float = 0.0

    @property
    def exit_code(self) -> int:
        if self.stop is None:
            return 0
        return {"cap": 3, "auth": 5, "access": 5, "key_expiry": 5}.get(self.stop, 4)


class Runner:
    def __init__(self, cfg: Config, phase: str, client, *, tiers=None, limit_pairs: int | None = None,
                 progress: bool = True, say=None, sleep=time.sleep, key_path=None, version: str | None = None,
                 key_expires: datetime | None = None, clock=_utc_now, heartbeat_seconds: float = 30.0,
                 heartbeat_clock=time.monotonic, heartbeat_thread: bool = True):
        """key_expires: the timezone-aware time the API key stops working (required for every phase but dev).
        clock: returns the current timezone-aware time; a test passes a fake. The heartbeat arguments are for tests too."""
        self.cfg, self.phase, self.client = cfg, phase, client
        self.tiers = tuple(tiers) if tiers else ALL_TIERS
        bad = set(self.tiers) - set(ALL_TIERS)
        if bad:
            raise RunnerError(f"unknown tiers {sorted(bad)}")
        self.limit_pairs, self.progress, self.sleep, self.key_path = limit_pairs, progress, sleep, key_path
        self.version = version
        self.say = say or (lambda msg: tqdm.write(msg))
        self.report = RunReport(phase, cap=cfg.caps_usd[phase])
        self.key_expires, self.clock = key_expires, clock
        self._pair_durations: list[timedelta] = []   # pairs that ran start to finish in this run
        self.heartbeat = Heartbeat(self.say, heartbeat_seconds, heartbeat_clock)
        self._heartbeat_thread = heartbeat_thread

    # ------------------------------------------------------------------ setup
    def _prepare(self):
        cfg, phase = self.cfg, self.phase
        ph = cfg.phases.get(phase)
        if ph is None:
            raise RunnerError(f"the config has no section for phase {phase!r}")
        counts = {t: ph.pairs_per_tier[t] for t in ALL_TIERS}
        if sum(counts.values()) == 0:
            raise RunnerError(f"the config plans no pairs for phase {phase!r}; set phases.{phase}.pairs_per_tier first")
        self.say(f"[1/5] phase {phase}: reading the seed list {ph.seed_file}")
        self.seeds = plan.read_seed_list(ph.seed_file)
        plan.check_phase_seeds(phase, self.seeds)
        others = {}
        for name, other in cfg.phases.items():
            if name != phase and name in REAL_PHASES and other.seed_file.exists():
                others[name] = plan.read_seed_list(other.seed_file)
        plan.check_disjoint(phase, self.seeds, others)
        for t in self.tiers:
            if counts[t] > len(self.seeds):
                raise RunnerError(f"the {phase} seed list has {len(self.seeds)} seeds but {t} needs {counts[t]}")
        self.say(f"[2/5] price file {cfg.price_file.name}: checking every model has a price")
        self.prices = PriceTable.load(cfg.price_file)
        for t in self.tiers:
            if counts[t] > 0:
                self.prices.require(cfg.models[t])
        self.say("[3/5] loading prompt and question files")
        self.system = {c: read_text_file(cfg.prompt_files[c], f"{c} system prompt") for c in CONDITIONS}
        self.checkin = read_text_file(cfg.prompt_files["checkin_question"], "check-in question")
        self.say("[4/5] reading the spend ledger and episode manifest")
        self.ledger = Ledger(cfg.runs_dir, phase, cfg.caps_usd[phase], self.prices)
        self.phase_dir = cfg.runs_dir / phase
        self.manifest = Manifest(self.phase_dir / "manifest.jsonl")
        blinded = phase in cfg.blinded_phases
        self.labels = {c: blinding.condition_code(c, blinded=blinded, path=self.key_path) for c in CONDITIONS}
        self.blinded = blinded
        if self.version is None:
            self.version = code_version()
        counts_sel = {t: counts[t] if t in self.tiers else 0 for t in ALL_TIERS}
        counts_sel = {t: n for t, n in counts_sel.items() if n}
        full = plan.build_slots(counts, cfg.shuffle_seed, ph.order)
        self.slots = [s for s in full if s[0] in self.tiers]
        if self.limit_pairs is not None:
            self.slots = self.slots[: self.limit_pairs]
        self.say(f"[5/5] {len(self.slots)} pairs planned ({counts_sel}), spend so far ${self.ledger.spend:.4f} of ${self.ledger.cap:.2f}")

    def _adopt_orphans(self):
        """A log with no manifest line is an episode a hard stop cut off. It counts as a crash: its pair is excluded."""
        known = self.manifest.logged_paths()
        for tier in ALL_TIERS:
            for f in sorted((self.phase_dir / "logs" / tier).glob("*.jsonl.gz")):
                if str(f) in known:
                    continue
                seed = int(f.name.split("-", 1)[0])
                self.manifest.append({"type": "pair_excluded", "tier": tier, "seed": seed,
                                      "reason": f"orphan log {f.name}: an earlier run stopped hard mid-episode"})
                self.report.exclusions.append((tier, seed, "orphan log"))
                self.say(f"  excluded {tier} seed {seed}: orphan log {f.name} from an interrupted run")

    # ------------------------------------------------------------------ the key's expiry
    def _say_key_hours(self):
        left = (self.key_expires - self.clock()).total_seconds() / 3600
        when = _fmt_time(self.key_expires)
        self.say(f"The key has {left:.1f} hours left (it expires at {when})." if left >= 0
                 else f"The key expired {-left:.1f} hours ago (at {when}).")

    def _pair_estimate(self) -> timedelta:
        d = self._pair_durations
        return sum(d, timedelta()) / len(d) if d else DEFAULT_PAIR_ESTIMATE

    def _key_ok(self) -> bool:
        """False (and the run stopped) if now + twice the estimated pair time + 1 hour would pass the key's expiry."""
        if self.key_expires is None:
            return True
        if self.clock() + 2 * self._pair_estimate() + EXPIRY_MARGIN <= self.key_expires:
            return True
        msg = (f"The key expires at {_fmt_time(self.key_expires)}. Stopping before the next pair so no batch straddles it. "
               f"Put a new key in the vault and rerun with its new expiry.")
        self._stop("key_expiry", msg, message=msg)
        return False

    # ------------------------------------------------------------------ the loop
    def run(self) -> RunReport:
        require_key_expires(self.phase, self.key_expires)
        if self.key_expires is not None:
            self._say_key_hours()
        self._prepare()
        self._adopt_orphans()
        total = 2 * len(self.slots)
        bar = tqdm(total=total, desc=f"{self.phase} episodes", unit="ep", dynamic_ncols=True, disable=not self.progress)
        self._bar = bar
        self.heartbeat.update(phase=self.phase, pairs=len(self.slots), cap=self.ledger.cap, spend=self.ledger.spend)
        if self._heartbeat_thread:
            self.heartbeat.start()
        consecutive = 0
        try:
            for i, (tier, k) in enumerate(self.slots, 1):
                while True:
                    active = [s for s in self.seeds if s not in self.manifest.excluded_seeds(tier)]
                    if k >= len(active):
                        self._stop("seed_list", f"the {tier} seed list has no seed left for slot {k + 1}")
                        break
                    if not self._key_ok():
                        break
                    seed = active[k]
                    self.heartbeat.update(pair=i, model=self.cfg.models[tier], turn="-", max_turns="-")
                    self.say(f"pair {i}/{len(self.slots)}: {tier} seed {seed}")
                    started, ran_before = self.clock(), self.report.episodes_run
                    outcome = self._run_pair(tier, seed)
                    if outcome == "done" and self.report.episodes_run - ran_before == 2:
                        self._pair_durations.append(self.clock() - started)  # only pairs this run played in full
                    self._tick()
                    if outcome == "done":
                        consecutive = 0
                        self.report.pairs_done += 1
                        break
                    if outcome == "halt":
                        break
                    consecutive += 1
                    if consecutive >= self.cfg.max_consecutive_exclusions:
                        self._stop("exclusions", f"{consecutive} exclusions in a row; something systematic is wrong")
                        break
                if self.report.stop:
                    break
        finally:
            self.heartbeat.close()
            bar.close()
        self.report.spend = self.ledger.spend
        self.say(f"finished: {self.report.pairs_done} pairs, {self.report.episodes_run} episodes run, "
                 f"{len(self.report.exclusions)} exclusions, spend ${self.report.spend:.4f} of ${self.report.cap:.2f}"
                 + (f", STOPPED: {self.report.stop}" if self.report.stop else ""))
        return self.report

    def _tick(self):
        spend = self.ledger.spend
        self.heartbeat.update(spend=spend)
        self._bar.set_postfix_str(f"phase spend ${spend:.2f}/${self.ledger.cap:.0f} ({100 * spend / self.ledger.cap:.0f}%)"
                                  if self.ledger.cap else "")

    def _on_turn(self, turn: int, max_turns: int):
        self.heartbeat.update(turn=turn, max_turns=max_turns, spend=self.ledger.spend)
        self.heartbeat.beat()

    def _stop(self, why: str, detail: str, *, message: str | None = None):
        """Stop the whole run. message, when given, is the one line printed instead of the generic STOP line."""
        self.report.stop = why
        self.manifest.append({"type": "halt", "reason": why, "detail": detail})
        self.say(message or f"STOP ({why}): {detail}")

    def _run_pair(self, tier: str, seed: int) -> str:
        """"done", "excluded" or "halt"."""
        stakes_turns = None
        for condition in CONDITIONS:  # stakes first, then no_stakes
            rec = self.manifest.done(tier, seed, self.labels[condition])
            if rec is not None:
                self.say(f"  {tier} seed {seed} {self.labels[condition]}: already done, skipping")
                self._bar.update(1)
            else:
                outcome = self._episode(tier, seed, condition, max_turns=stakes_turns)
                if outcome == "excluded":
                    self.manifest.append({"type": "pair_excluded", "tier": tier, "seed": seed,
                                          "reason": f"{condition} twin was excluded"})
                    return "excluded"
                if outcome == "halt":
                    return "halt"
                rec = self.manifest.done(tier, seed, self.labels[condition])
            if condition == "stakes":
                stakes_turns = rec["turns"]
        return "done"

    def _episode(self, tier: str, seed: int, condition: str, *, max_turns: int | None) -> str:
        cfg, model, label = self.cfg, self.cfg.models[tier], self.labels[condition]
        chk = self.ledger.start_check(model, cfg.priors_usd[tier])
        if not chk.ok:
            self._stop("cap", f"will not start {tier} seed {seed}: {chk.message()}")
            return "halt"
        # A twin that was stopped part way (key refused, cap) is played again on the same seed. Its first log stays
        # as it is, so the redo writes a new file and books its spend under a new episode id.
        attempt = self.manifest.attempts(tier, seed, label)
        again = f".r{attempt}" if attempt else ""
        episode_id = f"{self.phase}:{tier}:{seed}:{label}" + (f":r{attempt}" if attempt else "")
        log_path = self.phase_dir / "logs" / tier / f"{seed}-{label}{again}.jsonl.gz"
        if log_path.exists():
            raise RunnerError(f"episode log already exists and will not be overwritten: {log_path}")
        critter = ClaudeCritter(self.client, model=model, system_prompt=self.system[condition], ledger=self.ledger,
                                episode_id=episode_id, max_tokens=cfg.max_tokens, effort=cfg.effort,
                                max_retries=cfg.max_retries, backoff_base=cfg.backoff_base_seconds,
                                backoff_max=cfg.backoff_max_seconds, sleep=self.sleep)
        self.say(f"  {tier} seed {seed} {label}: starting (max_turns {max_turns or 48}, {chk.message()})"
                 + (f", redo {attempt}" if attempt else ""))
        self.report.episodes_run += 1
        try:
            result = play_episode(
                critter, condition=condition, seed=seed, log_path=log_path, model=model, condition_code=label,
                checkin_question=self.checkin, max_turns=max_turns, version=self.version,
                header_extra={"phase": self.phase, "tier": tier, "episode_id": episode_id, "attempt": attempt,
                              "effort": cfg.effort, "max_tokens": cfg.max_tokens, "price_file": cfg.price_file.name},
                progress=self.progress, desc=f"  {tier} {seed} {label}",
                status_suffix=lambda: f"phase ${self.ledger.spend:.2f}/${self.ledger.cap:.0f}", on_turn=self._on_turn)
        except (LedgerError, PriceError, RunnerError):
            raise
        except Exception as exc:  # a harness crash: excluded and replaced
            status, summary = "crash", {"turns": 0, "cost_usd": self.ledger.episode_cost(episode_id)}
            error = f"{type(exc).__name__}: {str(exc)[:200]}"
        else:
            status, summary, error = result["status"], result["summary"], None
        self.ledger.record_episode_end(model=model, episode_id=episode_id, status=status)
        self.manifest.append({
            "type": "episode", "phase": self.phase, "tier": tier, "model": model, "seed": seed, "condition_code": label,
            "episode_id": episode_id, "status": status, "turns": summary["turns"], "fainted": summary.get("fainted"),
            "cost_usd": summary["cost_usd"], "log_path": str(log_path), "error": error or summary.get("error"),
        })
        if status == "done":
            self.say(f"  {tier} seed {seed} {label}: done, {summary['turns']} turns, ${summary['cost_usd']:.4f}")
            self._bar.update(1)
            return "done"
        if status == "aborted_cap":
            self._stop("cap", f"spend crossed the cap during {tier} seed {seed} {label}; episode marked aborted_cap")
            return "halt"
        if status == "incomplete_auth":
            # Not an exclusion: the pair is not dropped, and a rerun plays this twin again on the same seed.
            self._stop("auth", f"the API refused the key during {tier} seed {seed} {label}; episode marked incomplete_auth",
                       message=AUTH_LINE)
            return "halt"
        if status == "stopped_access":
            # Not an exclusion either, and never a reason to try another model: the run stops and a rerun plays this twin again.
            self._stop("access", f"the API refused access to {model} during {tier} seed {seed} {label}; "
                                 f"episode marked stopped_access", message=ACCESS_LINE)
            return "halt"
        reason = error or (summary.get("error") or {}).get("message", status)
        self.report.exclusions.append((tier, seed, f"{condition}: {status}"))
        self.say(f"  EXCLUDED {tier} seed {seed} {label}: {status} ({reason}); its seed will be replaced")
        return "excluded"


# ---------------------------------------------------------------------- command line
def _question_if_present(cfg: Config) -> str | None:
    """The check-in question, so the fake client can tell a check-in turn. A missing file is not handled here:
    the Runner refuses to start on it."""
    try:
        return read_text_file(cfg.prompt_files["checkin_question"], "check-in question")
    except ConfigError:
        return None


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="runner.run", description=__doc__.split("\n\n")[0], allow_abbrev=False)
    ap.add_argument("--phase", required=True, choices=PHASES)
    ap.add_argument("--client", choices=("fake", "claude"), default="fake",
                    help="fake needs nothing; claude needs STAKES_ALLOW_API=yes in this process")
    ap.add_argument("--config", default=None, help="config file (default runner/config.json); caps live only there")
    ap.add_argument("--tiers", default=None, help="comma-separated subset of haiku,sonnet,opus,fable,mythos")
    ap.add_argument("--limit-pairs", type=int, default=None, help="run at most this many pairs (can only lower the plan)")
    ap.add_argument("--key-expires", default=None,
                    help="when the API key expires, ISO 8601 with an offset, e.g. 2026-12-03T21:35-06:00. "
                         "Required for every phase except dev; no pair starts if it could run past this time")
    ap.add_argument("--no-progress", action="store_true", help="no progress bars (status lines still print)")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    print(gate.mode_line(), flush=True)
    try:
        key_expires = parse_key_expires(args.key_expires) if args.key_expires is not None else None
        require_key_expires(args.phase, key_expires)  # before the gate, the config or any file
        if gate.api_allowed():
            gate.preflight()  # before anything else: no config read, no ledger, no log file
        cfg = load_config(args.config)
        if args.client == "claude":
            if args.phase not in REAL_PHASES:
                raise RunnerError("the dev phase runs on the fake client only, so it can never spend real money")
            client = gate.make_claude_client()
        else:
            client = FakeClient(random_valid_script(cfg.shuffle_seed, checkin_text=_question_if_present(cfg)))
        tiers = [t.strip() for t in args.tiers.split(",") if t.strip()] if args.tiers else None
        report = Runner(cfg, args.phase, client, tiers=tiers, limit_pairs=args.limit_pairs,
                        progress=not args.no_progress, key_expires=key_expires).run()
    except (gate.PreflightError, gate.ApiNotAllowed, ConfigError, PriceError, LedgerError, RunnerError) as e:
        print(f"error: {e}", file=sys.stderr, flush=True)
        return 2
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
