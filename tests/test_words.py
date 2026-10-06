from app import tools
from app.words import day, ordinal, say

BODEN = "V85_2026-10-03_11_5"


def test_say_uses_english_as_the_key():
    assert say("en", "Leg {leg}, {track}", leg=7, track="Boden") == "Leg 7, Boden"
    assert say("sv", "Leg {leg}, {track}", leg=7, track="Boden") == "Avdelning 7, Boden"
    assert say("sv", "Not translated yet") == "Not translated yet"  # falls back to English


def test_swedish_dates_and_placings():
    assert day("2026-10-03T15:08:18", "en") == "Saturday 3 October"
    assert day("2026-10-03T15:08:18", "sv") == "lördag 3 oktober"
    assert [ordinal(n, "sv") for n in (1, 2, 3, 11, 12, 21, 22)] == ["1:a", "2:a", "3:e", "11:e", "12:e", "21:a", "22:a"]
    assert ordinal(1.5, "sv") == "1,5" and ordinal(1.5) == "1.5"


def test_tool_tables_follow_the_language_but_facts_stay_english(load):
    games = [load(BODEN, True)]
    facts, view = tools.leg_details(games, "V85", "Boden", 7, "sv")
    assert view["title"] == "Avdelning 7, Boden"
    assert [c["label"] for c in view["columns"]] == ["Häst", "V-odds", "V85%", "Plac."]
    assert "The winner was Frank S.H. at odds 2.49." in facts
