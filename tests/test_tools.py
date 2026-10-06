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


@pytest.mark.parametrize("name, args, english, swedish", [
    ("leg_details", {"game_type": "V85", "leg": 1, "track": "boden"},
     "Looking at leg 1 at Boden", "Tittar på avdelning 1 på Boden"),
    ("favourite_stats", {"game_type": "V85"}, "Looking at the V85 favourites", "Tittar på favoriterna i V85"),
    ("compare_game_types", {}, "Comparing all game types", "Jämför alla spelformer"),
    ("game_overview", {"game_type": "V85", "track": "solvalla"},
     "Looking at the latest V85 game at Solvalla", "Tittar på den senaste V85-omgången på Solvalla"),
    ("upsets", {"game_type": "V85"}, "Looking at the V85 upsets", "Tittar på skrällarna i V85"),
    ("bets_vs_odds", {"game_type": "V85"},
     "Looking at bets against the odds in V85", "Tittar på spelprocent mot odds i V85"),
    ("find_horse", {"name": "Intro"}, "Looking for the horse Intro", "Letar efter hästen Intro"),
    ("make_tea", {}, "Looking at the race data", "Tittar på loppen"),
])
def test_status_for_every_tool_in_both_languages(v85, name, args, english, swedish):
    assert tools.looking(name, args, "V85", v85, "en") == english
    assert tools.looking(name, args, "V85", v85, "sv") == swedish


def test_status_names_the_track_the_tool_will_use(v85):
    assert tools.looking("leg_details", {"leg": 3}, "V85", v85) == "Looking at leg 3 at Boden"  # the latest game
    assert tools.looking("game_overview", {"track": "  Solvalla "}, "V85", v85) == "Looking at the latest V85 game at Solvalla"
    assert tools.looking("leg_details", {"leg": 3, "track": "Kalmar"}, "V85", v85) == "Looking at leg 3 at Kalmar"
    # Another game type's games are not loaded yet: the track as written, or none
    assert tools.looking("leg_details", {"game_type": "V86", "leg": 3, "track": "Åby"}, "V85", v85) == "Looking at leg 3 at Åby"
    assert tools.looking("leg_details", {"game_type": "V86", "leg": 3}, "V85", v85) == "Looking at leg 3 in V86"
    assert tools.looking("game_overview", {"game_type": "V86"}, "V85", v85, "sv") == "Tittar på den senaste V86-omgången"
    assert tools.looking("game_overview", {}, "V85", []) == "Looking at the latest V85 game"  # no finished games


def test_status_falls_back_for_bad_arguments(v85):
    general = "Looking at the race data"
    for leg in (None, "7", 7.5, True, 0, -1, 10**30):
        assert tools.looking("leg_details", {"leg": leg}, "V85", v85) == general
    for horse in (None, "", "ab", 42, "x" * 41, {"name": "Intro"}):
        assert tools.looking("find_horse", {"name": horse}, "V85", v85) == general
    assert tools.looking("favourite_stats", {"game_type": "V99"}, "V85", v85) == "Looking at the V85 favourites"  # like run()
    assert tools.looking("leg_details", {"game_type": "V86", "leg": 2, "track": ["Åby"]}, "V85", v85) == "Looking at leg 2 in V86"
    assert tools.looking("find_horse", {"name": "Frank\nS.H."}, "V85", v85) == "Looking for the horse Frank S.H."
