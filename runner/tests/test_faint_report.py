from runner.faint_report import cause, report, rows
from world.log import EpisodeLog


def _log(path, code, turns, end):
    with EpisodeLog(path, arm="arm1", model="m", condition_code=code, world_seed=7, start_map=[], version="v") as log:
        for t in turns:
            log.turn({k: t.get(k) for k in ("turn", "position", "move", "chosen_region", "shown_region", "energy",
                                              "health", "points", "diary", "tamper", "tamper_type", "raw_reply",
                                              "checkin", "checkin_answer", "tokens_in", "tokens_out", "cost_usd")})
        log.end(end)


def test_cause_reads_the_last_turn():
    assert cause({"fainted": False}, {"energy": 0}) == "-"
    assert cause({"fainted": True}, {"energy": 1, "health": 3}) == "energy"   # meters are shown before the move
    assert cause({"fainted": True}, {"energy": 5, "health": 4}) == "health"
    assert cause({"fainted": True}, None) == "unknown"
    assert cause({"fainted": True, "final_energy": 0, "final_health": 3}, {"energy": 1}) == "energy"
    assert cause({"fainted": True, "final_energy": 4, "final_health": 0}, {"energy": 5}) == "health"
    assert cause({"fainted": True, "final_energy": 0, "final_health": 0}, {"energy": 1}) == "both"


def test_only_stakes_logs_are_read(tmp_path):
    _log(tmp_path / "logs" / "haiku" / "7-stakes.jsonl.gz", "stakes",
         [{"turn": 1, "energy": 2, "health": 9}, {"turn": 2, "energy": 1, "health": 9}],
         {"status": "done", "turns": 2, "fainted": True, "food_eaten": 0, "thorns_hit": 1})
    _log(tmp_path / "logs" / "haiku" / "7-no_stakes.jsonl.gz", "no_stakes", [{"turn": 1}],
         {"status": "done", "turns": 2, "fainted": False})
    rs = rows(tmp_path)
    assert [(r["tier"], r["cause"]) for r in rs] == [("haiku", "energy")]
    assert "haiku: 1 stakes episodes, energy 1, health 0, both 0, unknown 0" in "\n".join(report(rs))
