"""Each data trap we found in ATG's API has a test here."""
from app.clean import finish_label

BODEN = "V85_2026-10-03_11_5"     # 3 scratched horses in leg 2
SOLVALLA = "V85_2026-09-27_5_5"   # favourite disqualified in leg 3
ORKLA = "V65_2026-10-04_83_2"     # Norwegian track, only the top 3 published
DD = "dd_2026-10-04_14_9"         # Dagens Dubbel, no V-game pool


def names(leg):
    return [r.name for r in leg.runners]


def test_scratched_horses_are_dropped(load):
    leg2 = load(BODEN, True).legs[1]
    numbers = [r.number for r in leg2.runners]
    assert not {1, 8, 10} & set(numbers)  # the scratched ones (they have odds 0)
    assert all(r.odds > 0 for r in leg2.runners)
    assert leg2.runners[0].name == "Readly Brodde"  # the real favourite at 1.35


def test_runners_sorted_by_odds_and_odds_converted(load):
    leg1 = load(BODEN, True).legs[0]
    odds = [r.odds for r in leg1.runners]
    assert odds == sorted(odds)
    assert (leg1.runners[0].name, leg1.runners[0].odds) == ("R.K.Kiara", 2.25)  # stored as 225


def test_disqualified_uses_the_flag_not_the_fake_finish_order(load):
    favourite = load(SOLVALLA, True).legs[2].runners[0]
    assert favourite.finish == "disqualified"


def test_place_zero_still_has_a_real_position():
    assert finish_label({"place": 0, "finishOrder": 11}) == "11"


def test_gallop_race_without_place_uses_finish_order():
    assert finish_label({"finishOrder": 6}) == "6"


def test_foreign_track_only_publishes_top_three(load):
    leg1 = load(ORKLA, True).legs[0]
    assert leg1.runners[0].finish == "unplaced"  # favourite Millie, outside the top 3
    assert sorted(r.finish for r in leg1.runners if r.finish != "unplaced") == ["1", "2", "3"]


def test_bet_share_only_exists_for_v_games(load):
    assert all(r.bet_share is None for leg in load(DD, True).legs for r in leg.runners)
    leg7 = load(BODEN, True).legs[6]
    assert {r.name: r.bet_share for r in leg7.runners}["Frank S.H."] == 46.33


def test_game_info(load):
    game = load(BODEN, True)
    assert (game.id, game.track, len(game.legs)) == (BODEN, "Boden", 8)
