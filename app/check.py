"""Step 4: the same answers worked out by plain code, used to check the LLM.

Rules:
- The favourite is the horse with the lowest final V-odds (see clean.py for ties).
- A disqualified horse counts as finishing last.
- "unplaced" (foreign tracks only publish the top 3) counts as "at least one place
  behind the last published place". A median built on it is a lower bound.
"""
from .clean import Leg


def leg_answer(leg: Leg) -> dict:
    """The correct answer for one leg, in the same shape the LLM answers in."""
    favourite = leg.runners[0]
    return {
        "favourites": [runner.name for runner in leg.runners[:3]],
        "odds": [round(runner.odds, 2) for runner in leg.runners[:3]],
        "position": favourite.finish,
        "won": favourite.finish == "1",
    }


def compare(llm: dict, truth: dict) -> dict:
    """One check per question. The favourites need the right names and V-odds. Where the favourite
    finished only counts when the model asked about the right horse, not by lucky coincidence."""
    right_horse = llm["favourites"][:1] == truth["favourites"][:1]
    return {
        "favourites": llm["favourites"] == truth["favourites"] and llm.get("odds") == truth["odds"],
        "position": right_horse and llm["position"] == truth["position"],
        "won": right_horse and llm["won"] == truth["won"],
    }


def position(label: str, leg: Leg) -> tuple[int, bool]:
    """A finish label as a number for the median, plus whether that number is exact."""
    if label == "disqualified":
        return len(leg.runners), True
    if label == "unplaced":
        known = [int(r.finish) for r in leg.runners if r.finish.isdigit()]
        return max(known, default=0) + 1, False
    return int(label), True


def summary(answers: list[tuple[dict, Leg]]) -> dict:
    """Win count, win rate and median finish of the favourite over all legs."""
    wins = sum(answer["won"] for answer, _ in answers)
    values = sorted(position(answer["position"], leg) for answer, leg in answers)
    middle = values[(len(values) - 1) // 2 : len(values) // 2 + 1]  # 1 value if odd, 2 if even
    return {
        "legs": len(answers),
        "wins": wins,
        "win_rate": wins / len(answers),
        "median": sum(value for value, _ in middle) / len(middle),
        "median_exact": all(exact for _, exact in middle),
    }


def odds_win_rate(legs: list[Leg]) -> float:
    """How often the odds said the favourite would win, on average over the legs."""
    chances = [(1 / leg.runners[0].odds) / sum(1 / r.odds for r in leg.runners) for leg in legs]
    return sum(chances) / len(chances)
