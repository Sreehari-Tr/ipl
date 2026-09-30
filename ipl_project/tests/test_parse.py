"""
Tests for parse.py.  Run with:   python -m pytest tests -v

Each test builds a tiny fake match and checks one cricket rule.
If a test fails, the parser is counting something wrongly.
"""
from src import parse


# ---------------------------------------------------------------------------
# Helpers that build fake data
# ---------------------------------------------------------------------------
def make_delivery(batter="Bat A", bowler="Bowl X", runs_batter=0,
                  extras=None, wickets=None):
    """One fake ball. `extras` example: {"wides": 1}."""
    extras = extras or {}
    runs_extras = sum(extras.values())
    delivery = {
        "batter": batter,
        "bowler": bowler,
        "non_striker": "Bat B",
        "runs": {"batter": runs_batter, "extras": runs_extras,
                 "total": runs_batter + runs_extras},
    }
    if extras:
        delivery["extras"] = extras
    if wickets:
        delivery["wickets"] = wickets
    return delivery


def make_match(first_innings_overs, second_innings_overs=None, super_over=False):
    """A fake match. Each 'overs' argument is a list of lists of deliveries."""
    def to_overs(overs):
        return [{"over": i, "deliveries": d} for i, d in enumerate(overs)]

    innings = [{"team": "Team One", "overs": to_overs(first_innings_overs)}]
    if second_innings_overs is not None:
        innings.append({"team": "Team Two", "overs": to_overs(second_innings_overs),
                        "target": {"runs": 10, "overs": 20}})
    if super_over:
        innings.append({"team": "Team Two", "super_over": True,
                        "overs": to_overs([[make_delivery(runs_batter=6)]])})
    return {
        "info": {
            "teams": ["Team One", "Delhi Daredevils"],
            "dates": ["2015-04-10"],
            "venue": "Feroz Shah Kotla, Delhi",
            "toss": {"winner": "Team One", "decision": "bat"},
            "outcome": {"winner": "Team One", "by": {"runs": 5}},
            "players": {"Team One": ["Bat A"], "Delhi Daredevils": ["Bowl X"]},
            "registry": {"people": {"Bat A": "id_a", "Bat B": "id_b", "Bowl X": "id_x"}},
        },
        "innings": innings,
    }


def first_ball(match_dict):
    _, balls, _ = parse.parse_match_dict(match_dict, "m1")
    return balls[0]


# ---------------------------------------------------------------------------
# Ball-level rules
# ---------------------------------------------------------------------------
def test_wide_is_not_legal_and_not_faced():
    ball = first_ball(make_match([[make_delivery(extras={"wides": 1})]]))
    assert ball["is_legal_ball"] is False
    assert ball["is_ball_faced"] is False
    assert ball["runs_bowler"] == 1          # bowler is charged for the wide


def test_noball_is_not_legal_but_is_faced():
    ball = first_ball(make_match([[make_delivery(runs_batter=4, extras={"noballs": 1})]]))
    assert ball["is_legal_ball"] is False
    assert ball["is_ball_faced"] is True
    assert ball["runs_batter"] == 4
    assert ball["runs_bowler"] == 5          # 4 off the bat + 1 no-ball


def test_legbye_is_not_charged_to_bowler_or_batter():
    ball = first_ball(make_match([[make_delivery(extras={"legbyes": 1})]]))
    assert ball["runs_batter"] == 0
    assert ball["runs_bowler"] == 0
    assert ball["runs_total"] == 1
    assert ball["is_legal_ball"] is True


def test_bowled_is_a_bowler_wicket():
    wicket = [{"kind": "bowled", "player_out": "Bat A"}]
    ball = first_ball(make_match([[make_delivery(wickets=wicket)]]))
    assert ball["is_dismissal"] is True
    assert ball["is_bowler_wicket"] is True
    assert ball["player_out_id"] == "id_a"


def test_run_out_is_not_a_bowler_wicket():
    wicket = [{"kind": "run out", "player_out": "Bat A"}]
    ball = first_ball(make_match([[make_delivery(wickets=wicket)]]))
    assert ball["is_dismissal"] is True
    assert ball["is_bowler_wicket"] is False


def test_retired_hurt_is_not_a_dismissal():
    wicket = [{"kind": "retired hurt", "player_out": "Bat A"}]
    ball = first_ball(make_match([[make_delivery(wickets=wicket)]]))
    assert ball["is_dismissal"] is False
    assert ball["is_bowler_wicket"] is False


# ---------------------------------------------------------------------------
# Match-level rules
# ---------------------------------------------------------------------------
def test_player_ids_come_from_registry():
    ball = first_ball(make_match([[make_delivery()]]))
    assert ball["batter_id"] == "id_a"
    assert ball["bowler_id"] == "id_x"


def test_team_and_venue_names_are_normalised():
    match_row, balls, _ = parse.parse_match_dict(make_match([[make_delivery()]]), "m1")
    assert match_row["team2"] == "Delhi Capitals"
    assert match_row["venue"] == "Arun Jaitley Stadium"
    assert balls[0]["bowling_team"] == "Delhi Capitals"


def test_super_over_is_excluded_from_balls():
    data = make_match([[make_delivery()]], [[make_delivery()]], super_over=True)
    _, balls, _ = parse.parse_match_dict(data, "m1")
    assert {b["innings_no"] for b in balls} == {1, 2}


def test_innings_totals_and_target():
    first = [[make_delivery(runs_batter=4), make_delivery(runs_batter=6)]]
    second = [[make_delivery(runs_batter=1)]]
    match_row, _, _ = parse.parse_match_dict(make_match(first, second), "m1")
    assert match_row["first_innings_runs"] == 10
    assert match_row["second_innings_runs"] == 1
    assert match_row["target"] == 10
    assert match_row["winner"] == "Team One"
    assert match_row["season"] == 2015


def test_delivery_numbering_and_phase():
    over = [make_delivery(extras={"wides": 1}), make_delivery(), make_delivery()]
    data = make_match([[make_delivery()]] * 15 + [over])   # 16th over -> index 15
    _, balls, _ = parse.parse_match_dict(data, "m1")
    last_over = [b for b in balls if b["over"] == 15]
    assert [b["delivery_in_over"] for b in last_over] == [1, 2, 3]
    assert all(b["phase"] == "death" for b in last_over)
    assert balls[0]["phase"] == "powerplay"


def test_match_without_innings_is_skipped():
    data = make_match([[make_delivery()]])
    data["innings"] = []
    assert parse.parse_match_dict(data, "m1") is None


def test_no_result_and_tie_outcomes():
    data = make_match([[make_delivery()]])
    data["info"]["outcome"] = {"result": "no result"}
    assert parse.parse_match_dict(data, "m1")[0]["result_type"] == "no_result"

    data["info"]["outcome"] = {"result": "tie", "eliminator": "Team One"}
    row = parse.parse_match_dict(data, "m1")[0]
    assert row["result_type"] == "tie"
    assert row["winner"] == "Team One"
