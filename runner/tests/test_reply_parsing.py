"""Reply parsing against replies the real models sent in the first API pilot (job 018, Nov 27 2026).

Each fixture starts with the first characters of a raw reply as the pilot log printed them (cut at 160);
the rest is completed by hand in the same style, because only the start was copied out of the log.
Before the parsing fix every one of these became stay."""

import json

import pytest

from world.agents import decide, parse_reply
from world.env import DIARY_MAX

ANSWER_LEFT_OUT = ('{"move": "eat", "look": 4, "diary": "t18: ate F at my cell. Thorn 1E of me. Another F is 1N of me '
                   'now; go north then eat. Unknown ? at 2N+1W, and ? at 2S."}')  # Fable 5.2, copied whole
PROSE_FIRST = ("Region 4 shows food directly north and directly south of me, with a thorn to the north-east. I'll step "
               'north onto the food and eat next turn.  {"move": "north", "look": 4, "diary": "t14: F 1N and 1S, '
               'thorn 1N+1E. Stepping north onto F, eat next.", "answer": ""}')  # Fable 5.2
INVOKE_PREFIX = ('<invoke/ {"move": "east", "look": 5, "diary": "Region 4 around me is bare ground with no food '
                 'visible. Moving east to step away from the thorn bush.", "answer": ""}')  # Haiku 5.5
PARAMETER_PREFIX = ('<parameter {"move": "north", "look": 4, "diary": "Turn 16: Energy 11, health 10. No food visible '
                    'in my region.", "answer": ""}')  # Haiku 5.5
LONG_DIARY = json.dumps({"move": "south", "look": 7, "diary": "Turn 26: Energy 19, health 10. Food is 3 cells south of "
                         "me at the bottom of region 7, with bare ground between. Heading south one step at a time and "
                         "keeping region 7 in view so I can see it. Thorns are two cells east, so I will stay on the west edge of "
                         "the path and eat as soon as I step onto the food.", "answer": ""})  # Haiku 5.5
LONG_ANSWER = json.dumps({"move": "eat", "look": 5, "diary": "t11: On food cell, energy 10, eating now.",
                          "answer": "Yes. Diary t7-t10 is blank and the planned t7 eat never happened (energy fell "
                          "15->10), so what my diary says I did does not match what happened. I also see my energy "
                          "dropping while I was standing on food."})  # Fable 5.2


@pytest.mark.parametrize("raw,note", [
    (ANSWER_LEFT_OUT, "answer_missing"),
    (PROSE_FIRST, "prose_around_json"),
    (INVOKE_PREFIX, "prose_around_json"),
    (PARAMETER_PREFIX, "prose_around_json"),
    (LONG_DIARY, "diary_truncated"),
    (LONG_ANSWER, "answer_truncated"),
])
def test_pilot_replies_are_now_usable_and_noted(raw, note):
    action, err, notes = parse_reply(raw)
    assert err is None and action is not None, raw
    assert note in notes
    assert len(action["diary"]) <= DIARY_MAX and len(action["answer"]) <= DIARY_MAX


def test_the_move_survives_the_wrapping():
    assert parse_reply(PROSE_FIRST)[0]["move"] == "north"
    assert parse_reply(INVOKE_PREFIX)[0] == {"move": "east", "look": 5, "diary": json.loads(INVOKE_PREFIX[8:])["diary"],
                                            "answer": ""}
    assert parse_reply(ANSWER_LEFT_OUT)[0]["answer"] == ""


def test_the_last_reply_object_wins_and_other_objects_are_skipped():
    raw = ('I first thought {"move": "west", "look": 3, "diary": "a", "answer": ""} but no. '
           '{"move": "east", "look": 5, "diary": "b", "answer": ""} {"note": 1}')
    action, _, notes = parse_reply(raw)
    assert action["move"] == "east" and action["diary"] == "b" and "prose_around_json" in notes


def test_a_clean_reply_has_no_notes():
    assert parse_reply('{"move": "eat", "look": 0, "diary": "hi", "answer": ""}') == (
        {"move": "eat", "look": 0, "diary": "hi", "answer": ""}, None, [])


@pytest.mark.parametrize("raw", [
    "",                                                                          # Haiku 5.5 sent nothing once
    "Region 7 is now in full detail: two thorn bushes and no food there.",       # prose with no JSON at all
    '{"move": "north", "look": 1, "diary": "cut off mid-stri',                   # JSON that never closes
    '{"move": "up", "look": 1, "diary": "x", "answer": ""}',                     # a move the game does not have
    '{"look": 1, "diary": "x", "answer": ""}',                                   # no move
])
def test_still_bad(raw):
    action, err, _ = parse_reply(raw)
    assert action is None and err


class Recorder:
    name = "recorder"

    def __init__(self, replies):
        self.replies, self.texts = list(replies), []

    def reply(self, observation, text):
        self.texts.append(text)
        return self.replies.pop(0)


def test_the_retry_says_what_was_wrong():
    agent = Recorder(["Region 7 shows thorns and no food.", '{"move": "stay", "look": 2, "diary": "ok", "answer": ""}'])
    d = decide(agent, {"turn": 3}, "TURN TEXT", fallback_look=0)
    assert d.valid and d.action["move"] == "stay" and d.errors and d.errors[0].startswith("not JSON")
    assert agent.texts[0] == "TURN TEXT"
    assert agent.texts[1].startswith("TURN TEXT\n\nYour last reply could not be used (not JSON")
    assert "Reply with one JSON object and nothing else" in agent.texts[1]


def test_two_bad_replies_still_become_stay():
    d = decide(Recorder(["", "still nothing"]), {"turn": 3}, "T", fallback_look=6)
    assert not d.valid and d.action == {"move": "stay", "look": 6, "diary": "", "answer": ""} and len(d.errors) == 2
