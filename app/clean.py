"""Step 2: turn ATG's raw game JSON into small, clean objects.

The data traps we found are all handled here:
- scratched horses have odds 0, so they are dropped
- a disqualified horse has a fake finishOrder (39 to 44), so we use the flag instead
- place 0 means "outside the prize places", the real position is in finishOrder
- foreign tracks only publish the top 3, everyone else is "unplaced"
"""
from dataclasses import dataclass


@dataclass
class Runner:
    number: int
    name: str
    odds: float              # final V-odds (win odds), e.g. 2.25
    bet_share: float | None  # % of the money in the V-game pool, None for games without one (dd, ld)
    finish: str              # "1", "2", ..., "disqualified" or "unplaced"


@dataclass
class Leg:
    number: int
    runners: list[Runner]  # horses that started, lowest odds first


@dataclass
class Game:
    id: str
    track: str  # "Solvalla", or "Åby & Solvalla" when the legs run at two tracks
    start: str  # start time of the first leg
    legs: list[Leg]


def parse_game(raw: dict) -> Game:
    game_type = raw["id"].split("_")[0]  # "V85_2026-10-03_11_5" -> "V85"
    legs = []
    for number, race in enumerate(raw["races"], start=1):
        runners = [runner for start in race["starts"] if (runner := parse_runner(start, game_type))]
        # Lowest odds first. Ties: more bet share first, then lower start number.
        runners.sort(key=lambda r: (r.odds, -(r.bet_share or 0), r.number))
        if runners:
            legs.append(Leg(number, runners))

    tracks = dict.fromkeys(race["track"]["name"] for race in raw["races"])  # unique, in order
    return Game(raw["id"], " & ".join(tracks), raw["races"][0]["startTime"], legs)


def parse_runner(start: dict, game_type: str) -> Runner | None:
    odds = start.get("pools", {}).get("vinnare", {}).get("odds")
    if start.get("scratched") or not odds:
        return None
    share = start["pools"].get(game_type, {}).get("betDistribution")
    return Runner(
        number=start["number"],
        name=start["horse"]["name"],
        odds=odds / 100,  # stored times 100: 225 means 2.25
        bet_share=None if share is None else share / 100,
        finish=finish_label(start.get("result", {})),
    )


def finish_label(result: dict) -> str:
    if result.get("disqualified"):
        return "disqualified"
    position = result.get("finishOrder") or result.get("place")
    return str(position) if position else "unplaced"
