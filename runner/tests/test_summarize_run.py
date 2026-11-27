from runner.summarize_run import blank_diary_lines, report


def test_blank_diary_lines_reads_each_turns_entry_from_the_next_turn():
    turns = [
        {"turn": 1, "diary": []},
        {"turn": 2, "diary": [{"turn": 1, "text": "went north"}]},
        {"turn": 3, "diary": [{"turn": 1, "text": "went north"}, {"turn": 2, "text": ""}]},
        {"turn": 4, "diary": [{"turn": 2, "text": " "}, {"turn": 3, "text": "ate"}]},
    ]
    assert blank_diary_lines(turns) == (1, 3)


def test_report_never_prints_yes_counts():
    s = {"groups": {("haiku", "stakes"): {"logs": 1, "episodes": 1, "turns": 48, "checkins": 4, "diary_counted": 47}},
         "halts": [], "exclusions": 0}
    text = "\n".join(report(s)).lower()
    assert "hit" not in text and "false alarm" not in text and "yes answers" not in text
