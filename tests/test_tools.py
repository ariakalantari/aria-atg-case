import pytest

from app import tools

BODEN = "V85_2026-10-03_11_5"
SOLVALLA = "V85_2026-09-27_5_5"
DD = "dd_2026-10-04_14_9"


@pytest.fixture
def v85(load):
    return [load(BODEN, True), load(SOLVALLA, True)]


def test_favourite_stats(v85):
    facts, view = tools.favourite_stats(v85, "V85")
    assert facts[0] == "In the latest 2 V85 games the favourite won 7 of 16 legs (44%)."
    assert view["tiles"][0] == {"label": "Favourite won", "value": "7 of 16"}
    assert [row["won"] for row in view["rows"]] == ["2 of 8", "5 of 8"]


def test_leg_details(v85):
    facts, view = tools.leg_details(v85, "V85", "Boden", 7)
    assert "The favourite was Shogun R.R. at odds 1.98, and it finished 2nd." in facts
    assert "The winner was Frank S.H. at odds 2.49." in facts
    assert [c["key"] for c in view["columns"]] == ["horse", "odds", "share", "finish"]
    assert view["rows"][0]["horse"] == {"number": 5, "name": "Shogun R.R."}


def test_leg_that_does_not_exist(v85):
    facts, view = tools.leg_details(v85, "V85", "", 9)
    assert facts == ["Leg 9 does not exist. The V85 game at Boden on Saturday 3 October has legs 1 to 8."]
    assert view is None


def test_no_bet_share_column_for_dd(load):
    _, view = tools.leg_details([load(DD, True)], "dd", "", 1)
    assert "share" not in [c["key"] for c in view["columns"]]


def test_track_names_match_loosely(v85):
    assert tools.pick_game(v85, "solvalla").track == "Solvalla"
    assert tools.pick_game(v85, "").track == "Boden"  # latest game
    assert tools.pick_game(v85, "Kalmar") is None
    assert tools.plain("Åby") == "aby" and tools.plain("Frank S.H.") == "franksh"


def test_unknown_track_lists_the_real_ones(v85):
    facts, view = tools.game_overview(v85, "V85", "Kalmar")
    assert "They were at: Boden (Saturday 3 October), Solvalla (Sunday 27 September)." in facts[0]
    assert view is None


def test_upsets_are_sorted_by_winner_odds(v85):
    facts, view = tools.upsets(v85, "V85")
    odds = [row["odds"] for row in view["rows"]]
    assert odds == sorted(odds, reverse=True) and len(odds) == 5
    assert facts[0].startswith("The biggest surprise in the latest V85 games was")


def test_bets_vs_odds(v85, load):
    facts, view = tools.bets_vs_odds(v85, "V85")
    legs = [(row["leg"]["track"], row["leg"]["leg"]) for row in view["rows"]]
    assert ("Boden", 7) in legs  # Shogun R.R. had the lowest odds, Frank S.H. the most bets
    facts, view = tools.bets_vs_odds([load(DD, True)], "dd")
    assert facts == ["dd has no V-game pool, so there is no bet share to compare with the odds."] and view is None


def test_find_horse(v85):
    facts, view = tools.find_horse(v85, "V85", "frank sh")
    assert facts == ["Frank S.H. ran leg 7 of V85 at Boden on Saturday 3 October at odds 2.49, "
                     "number 2 in the odds (not the favourite), and won."]
    assert tools.find_horse(v85, "V85", "Nobody")[1] is None


def test_compare_game_types(v85, load):
    facts, view = tools.compare_game_types({"V85": v85, "dd": [load(DD, True)], "V75": []})
    assert [row["game"] for row in view["rows"]] == ["V85", "dd"]  # sorted by win rate, V75 has no games
    assert facts[0].startswith("Favourites won most often in V85")


@pytest.mark.anyio
async def test_run_uses_the_page_game_type_and_handles_unknown_tools(v85, monkeypatch):
    asked = []

    async def fake_load(client, game_type):
        asked.append(game_type)
        return v85
    monkeypatch.setattr(tools, "load", fake_load)

    facts, view, label = await tools.run(None, "upsets", {}, "V85")
    assert asked == ["V85"] and label == "Looked for upsets in V85" and view
    facts, view, label = await tools.run(None, "make_tea", {}, "V85")
    assert facts == ["There is no tool called make_tea."] and view is None
