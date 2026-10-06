import pytest

from app import check
from app.clean import Leg, Runner

BODEN = "V85_2026-10-03_11_5"
SOLVALLA = "V85_2026-09-27_5_5"
ORKLA = "V65_2026-10-04_83_2"


def leg_with(*finishes: str) -> Leg:
    runners = [Runner(i, f"Horse {i}", 2.0 + i, None, f) for i, f in enumerate(finishes, start=1)]
    return Leg(1, runners)


def test_leg_answer(load):
    leg1 = load(BODEN, True).legs[0]
    assert check.leg_answer(leg1) == {
        "favourites": ["R.K.Kiara", "Arizona", "Sonoma L.A."],
        "odds": [2.25, 5.32, 7.67],
        "position": "1",
        "won": True,
    }


def test_compare_needs_the_right_odds_and_the_right_horse(load):
    truth = check.leg_answer(load(BODEN, True).legs[0])
    assert all(check.compare(truth, truth).values())
    wrong_odds = {**truth, "odds": [2.25, 5.32, 9.99]}
    assert check.compare(wrong_odds, truth)["favourites"] is False
    # Asked about the wrong horse, a matching finish is luck, not a right answer
    wrong_horse = {**truth, "favourites": ["Arizona", "R.K.Kiara", "Sonoma L.A."]}
    assert check.compare(wrong_horse, truth) == {"favourites": False, "position": False, "won": False}


def test_summary_over_real_games(load):
    legs = load(BODEN, True).legs + load(SOLVALLA, True).legs
    result = check.summary([(check.leg_answer(leg), leg) for leg in legs])
    assert result["legs"] == 16
    assert result["wins"] == 7  # 2 at Boden, 5 at Solvalla
    assert result["median"] == 2.0
    assert result["median_exact"]


def test_median_of_even_count_is_the_average_of_the_middle_two():
    a, b = leg_with("1", "2"), leg_with("3", "2")
    answers = [({"won": True, "position": "1"}, a), ({"won": False, "position": "3"}, b)]
    assert check.summary(answers)["median"] == 2.0


def test_disqualified_counts_as_last():
    assert check.position("disqualified", leg_with("1", "2", "3", "disqualified")) == (4, True)


def test_unplaced_is_a_lower_bound(load):
    leg1 = load(ORKLA, True).legs[0]  # top 3 published
    assert check.position("unplaced", leg1) == (4, False)
    result = check.summary([(check.leg_answer(leg1), leg1)])
    assert (result["median"], result["median_exact"]) == (4, False)


def test_compare():
    truth = {"favourites": ["A", "B", "C"], "position": "2", "won": False}
    llm = {"favourites": ["A", "C", "B"], "position": "2", "won": False}
    assert check.compare(llm, truth) == {"favourites": False, "position": True, "won": True}


def test_odds_win_rate_is_a_probability(load):
    rate = check.odds_win_rate(load(BODEN, True).legs)
    assert rate == pytest.approx(0.3647, abs=0.0001)  # the odds gave Boden's favourites 36% on average
