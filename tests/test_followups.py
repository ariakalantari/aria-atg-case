import pytest

from app import followups, tools
from app.words import answer_language

BODEN = "V85_2026-10-03_11_5"
SOLVALLA = "V85_2026-09-27_5_5"
DD = "dd_2026-10-04_14_9"


@pytest.fixture
def v85(load):
    return [load(BODEN, True), load(SOLVALLA, True)]


def after(name, args, facts_and_view, games, lang="en"):
    """Preset ideas after one tool call, the way chat() passes it: (call, view)."""
    facts, view = facts_and_view
    call = {"name": name, "arguments": args, "facts": facts}
    return followups.candidates([(call, view)], "V85", games, lang)


def test_after_a_leg_the_next_leg_comes_first(v85):
    ideas = after("leg_details", {"game_type": "V85", "leg": 7, "track": "boden"}, tools.leg_details(v85, "V85", "boden", 7), v85)
    assert ideas[:3] == ["Show leg 8 at Boden", "Show all legs at Boden", "Biggest upsets in V85"]
    last = after("leg_details", {"game_type": "V85", "leg": 8}, tools.leg_details(v85, "V85", "", 8), v85, "sv")
    assert last[:2] == ["Visa avdelning 7 på Boden", "Visa alla avdelningar på Boden"]  # no leg 9: the one before


def test_after_favourite_stats(v85):
    ideas = after("favourite_stats", {"game_type": "V85"}, tools.favourite_stats(v85, "V85"), v85)
    assert ideas[:4] == ["Biggest upsets in V85", "Compare all game types", "Is the favourite a good bet?", "Bets against odds in V85"]
    swedish = after("favourite_stats", {"game_type": "V85"}, tools.favourite_stats(v85, "V85", "sv"), v85, "sv")
    assert swedish[:3] == ["Största skrällarna i V85", "Jämför alla spelformer", "Lönar det sig att spela på favoriten?"]


def test_no_bet_share_ideas_for_dd(load):
    dd = [load(DD, True)]
    call = {"name": "favourite_stats", "arguments": {"game_type": "dd"}, "facts": []}
    ideas = followups.candidates([(call, tools.favourite_stats(dd, "dd")[1])], "dd", dd, "en")
    assert not any("Bets against odds" in idea for idea in ideas)


def test_after_compare_game_types(v85, load):
    facts, view = tools.compare_game_types({"V85": v85, "dd": [load(DD, True)]})
    best, worst = view["rows"][0]["game"], view["rows"][-1]["game"]
    ideas = after("compare_game_types", {}, (facts, view), v85)
    assert ideas[:2] == [f"Summarise {best}", f"Biggest upsets in {worst}"]


def test_after_game_overview_the_surprise_leg_and_the_other_game(v85):
    facts, view = tools.game_overview(v85, "V85", "Boden")
    surprise = max((r for r in view["rows"] if r["finish"] != "1" and r["winner"]), key=lambda r: r["winner_odds"])
    ideas = after("game_overview", {"game_type": "V85", "track": "Boden"}, (facts, view), v85)
    assert ideas[:2] == [f"Show leg {surprise['leg']['leg']} at Boden", "Show V85 at Solvalla"]


def test_after_upsets_bets_and_find_horse(v85):
    facts, view = tools.upsets(v85, "V85")
    top = view["rows"][0]["leg"]
    assert after("upsets", {"game_type": "V85"}, (facts, view), v85)[0] == f"Show leg {top['leg']} at {top['track']}"
    facts, view = tools.bets_vs_odds(v85, "V85")
    first = view["rows"][0]["leg"]
    assert after("bets_vs_odds", {"game_type": "V85"}, (facts, view), v85)[0] == f"Show leg {first['leg']} at {first['track']}"
    ideas = after("find_horse", {"name": "frank sh"}, tools.find_horse(v85, "V85", "frank sh"), v85, "sv")
    assert ideas[:2] == ["Visa avdelning 7 på Boden", "Visa alla avdelningar på Boden"]


def test_a_tool_that_found_nothing_gives_only_general_ideas(v85):
    ideas = after("leg_details", {"game_type": "V85", "leg": 9}, tools.leg_details(v85, "V85", "", 9), v85)
    assert ideas[0] == "Summarise V85"


def test_every_idea_reads_as_its_own_language(v85):
    """A chip clicked on a page in the other language is still answered in the chip's language."""
    turn = [({"name": "upsets", "arguments": {"game_type": "V85"}, "facts": []}, tools.upsets(v85, "V85")[1]),
            ({"name": "favourite_stats", "arguments": {"game_type": "V85"}, "facts": []}, None)]
    for lang, other in [("en", "sv"), ("sv", "en")]:
        for idea in followups.candidates(turn, "V85", v85, lang):
            assert answer_language(idea, other) == lang, idea
            assert len(idea) <= followups.MAX_LENGTH


def test_choose_keeps_good_picks_and_checks_the_own_question():
    ideas = ["Show leg 8 at Boden", "Biggest upsets in V85", "Summarise V85"]
    asked = {tools.plain("Show me leg 7 at Boden")}
    reply = {"picks": ["Summarise V85", "Made up idea"], "question": "  Who won leg 8 at Boden? "}
    assert followups.choose(reply, ideas, asked, "en") == ["Summarise V85", "Who won leg 8 at Boden?", "Show leg 8 at Boden"]
    # Wrong language, too long or cut off, already asked, or about what the answer already said:
    # the own question is dropped and preset ideas fill in
    answer = "Wiener Sängerknabe won leg 4 at Åby at odds 43.92."
    for question in ["Vem vann avdelning 8 på Boden?", "Who " + "really " * 10 + "won?", "Show me leg 7 at Boden",
                     "Who won Leg 4 at Åby?", "Which favourites lost?", "Which horses won at odds above twenty at Bo"]:
        reply = {"picks": ["Biggest upsets in V85", "Biggest upsets in V85"], "question": question}
        assert followups.choose(reply, ideas, asked, "en", answer) == ["Biggest upsets in V85", "Show leg 8 at Boden", "Summarise V85"]


@pytest.mark.anyio
async def test_suggest_falls_back_to_preset_ideas_when_the_model_fails(v85, monkeypatch):
    async def broken(client, prompt, schema):
        raise ValueError("not json")
    monkeypatch.setattr(followups.ask, "ask", broken)
    turn = [({"name": "upsets", "arguments": {"game_type": "V85"}, "facts": ["..."]}, tools.upsets(v85, "V85")[1])]
    messages = [{"role": "user", "content": "Biggest upsets?"}]
    questions = await followups.suggest(None, messages, "An answer.", turn, "V85", v85, "en")
    assert questions == followups.candidates(turn, "V85", v85, "en")[:3]


@pytest.mark.anyio
async def test_suggest_skips_what_was_already_asked(v85):
    messages = [{"role": "user", "content": "Summarise V85"}, {"role": "assistant", "content": "..."},
                {"role": "user", "content": "biggest upsets in v85"}]
    questions = await followups.suggest(None, messages, "Hi!", [], "V85", v85, "en")  # no tools: no model call
    assert questions == ["Compare all game types", "Is the favourite a good bet?", "Show leg 1 at Boden"]
