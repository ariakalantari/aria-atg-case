"""Tools the chat assistant can call: plain code over the cleaned race data.

The model decides when to call a tool and with which arguments. The tool returns:
- facts: short sentences the model reads before it answers (most important first, always English)
- view: a table (and maybe tiles) the page draws in ATG's style, in the page's language, or None
So the model talks, but every race fact comes from code.
"""
import asyncio
import unicodedata

import httpx

from . import check, clean, fetch, words
from .clean import Game, Leg, Runner
from .words import ordinal, say

GAME_TYPE = {"type": "string", "enum": fetch.GAME_TYPES}
TRACK = {"type": "string", "description": "Track name from the question or the conversation so far, "
         "for example Åby. Leave empty only when no track has been mentioned (then the latest game is used)."}


def tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    parameters = {"type": "object", "properties": properties, "required": required}
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


# What the model sees: names, descriptions and arguments of the tools
SCHEMAS = [
    tool("favourite_stats", "How the favourites did in ONE game type: how often the favourite won, its median "
         "finish and the win chance the odds gave, over the latest 3 games.", {"game_type": GAME_TYPE}, ["game_type"]),
    tool("compare_game_types", "Compare all game types at once: how often the favourite won in each. Use this for "
         "any question about which game type is best, most reliable or most surprising.", {}, []),
    tool("game_overview", "Every leg of one game (omgång): the favourite, the winner and their odds.",
         {"game_type": GAME_TYPE, "track": TRACK}, ["game_type"]),
    tool("leg_details", "Every horse in one leg (avdelning) with odds, bet share and finishing position. "
         "Use it to show or open a leg.",
         {"game_type": GAME_TYPE, "leg": {"type": "integer"}, "track": TRACK}, ["game_type", "leg"]),
    tool("upsets", "The biggest surprises (skrällar): legs won by horses with high odds.", {"game_type": GAME_TYPE}, ["game_type"]),
    tool("bets_vs_odds", "Legs where the horse with the most bets in the V-game pool was not the odds favourite.",
         {"game_type": GAME_TYPE}, ["game_type"]),
    tool("find_horse", "Find a horse by name in the latest games and show how it did.",
         {"name": {"type": "string"}, "game_type": GAME_TYPE}, ["name"]),
]


async def load(client: httpx.AsyncClient, game_type: str) -> list[Game]:
    return [clean.parse_game(raw) for raw in await fetch.recent_games(client, game_type)]


async def run(client: httpx.AsyncClient, name: str, args: dict, page_game_type: str,
              lang: str = "en") -> tuple[list[str], dict | None, str]:
    """Run one tool call from the model. Returns facts, view and a short label for the page."""
    if name == "compare_game_types":
        loaded = await asyncio.gather(*(load(client, t) for t in fetch.GAME_TYPES))
        facts, view = compare_game_types(dict(zip(fetch.GAME_TYPES, loaded)), lang)
        return facts, view, say(lang, "Compared every game type")

    game_type = args.get("game_type") if args.get("game_type") in fetch.GAME_TYPES else page_game_type
    games = await load(client, game_type)
    if not games:
        facts = [f"There are no finished {game_type} games right now."]
        return facts, None, say(lang, "Looked for {game_type} games", game_type=game_type)

    track = str(args.get("track") or "")
    where = getattr(pick_game(games, track), "track", track)  # the track actually used, shown in the label
    if name == "favourite_stats":
        return *favourite_stats(games, game_type, lang), say(lang, "Counted the favourites in {game_type}", game_type=game_type)
    if name == "game_overview":
        return *game_overview(games, game_type, track, lang), say(lang, "Opened {game_type} at {track}", game_type=game_type, track=where)
    if name == "leg_details":
        leg = args.get("leg") if isinstance(args.get("leg"), int) else 0
        return *leg_details(games, game_type, track, leg, lang), say(lang, "Looked up leg {leg} at {track}", leg=leg, track=where)
    if name == "upsets":
        return *upsets(games, game_type, lang), say(lang, "Looked for upsets in {game_type}", game_type=game_type)
    if name == "bets_vs_odds":
        return *bets_vs_odds(games, game_type, lang), say(lang, "Compared bets with odds in {game_type}", game_type=game_type)
    if name == "find_horse":
        horse = str(args.get("name") or "")
        return *find_horse(games, game_type, horse, lang), say(lang, "Searched for {horse}", horse=horse)
    return [f"There is no tool called {name}."], None, say(lang, "Tried an unknown tool")


# ---------- the tools ----------

def how_favourites_did(legs: list[Leg]) -> tuple[dict, float]:
    """Wins, win rate and median finish of the real favourites, and the win chance the odds gave them."""
    return check.summary([(check.leg_answer(leg), leg) for leg in legs]), check.odds_win_rate(legs)


def favourite_stats(games: list[Game], game_type: str, lang: str = "en"):
    summary, odds = how_favourites_did([leg for game in games for leg in game.legs])
    than = "more often than" if summary["win_rate"] > odds else "less often than" if summary["win_rate"] < odds else "as often as"
    facts = [
        f"In the latest {len(games)} {game_type} games the favourite won {summary['wins']} of "
        f"{summary['legs']} legs ({percent(summary['win_rate'])}).",
        f"The odds gave the favourite a {percent(odds)} chance to win on average, so the favourites won {than} "
        "the odds expected. That comparison is the fair yardstick, not 50%.",
        f"The favourite's median finishing position was {median_text(summary)}.",
    ]
    rows = []
    for game in games:
        wins = sum(leg.runners[0].finish == "1" for leg in game.legs)
        facts.append(f"{game.track} on {day(game)}: the favourite won {wins} of {len(game.legs)} legs.")
        rows.append({"game": f"{game.track}, {day(game, lang)}", "won": say(lang, "{a} of {b}", a=wins, b=len(game.legs))})
    view = {
        "title": say(lang, "Favourites in {game_type}", game_type=game_type),
        "game_type": game_type,
        "tiles": [
            {"label": say(lang, "Favourite won"), "value": say(lang, "{a} of {b}", a=summary["wins"], b=summary["legs"])},
            {"label": say(lang, "Median finish"), "value": median_text(summary, lang)},
            {"label": say(lang, "Odds expected"), "value": percent(odds)},
        ],
        "columns": [column("game", say(lang, "Game")), column("won", say(lang, "Favourite won"))],
        "rows": rows,
    }
    return facts, view


def compare_game_types(games_by_type: dict[str, list[Game]], lang: str = "en"):
    rows = []
    for game_type, games in games_by_type.items():
        legs = [leg for game in games for leg in game.legs]
        if legs:
            summary, odds = how_favourites_did(legs)
            rows.append({"game": game_type, "legs": summary["legs"], "won": summary["win_rate"],
                         "expected": odds, "median": summary})
    if not rows:
        return ["None of the game types has any finished games right now."], None
    rows.sort(key=lambda row: row["won"], reverse=True)
    best, worst = rows[0], rows[-1]
    facts = [
        f"Favourites won most often in {best['game']} ({percent(best['won'])} of {best['legs']} legs) "
        f"and least often in {worst['game']} ({percent(worst['won'])} of {worst['legs']} legs).",
        *(f"{r['game']}: the favourite won {percent(r['won'])} of {r['legs']} legs, "
          f"the odds expected {percent(r['expected'])}." for r in rows),
    ]
    for row in rows:
        row["median"] = median_text(row["median"], lang)
    view = {
        "title": say(lang, "Favourites in every game type"),
        "columns": [column("game", say(lang, "Game type"), "game"), column("legs", say(lang, "Legs")),
                    column("won", say(lang, "Fav. won"), "percent"), column("expected", say(lang, "Odds said"), "percent"),
                    column("median", say(lang, "Median"))],
        "rows": rows,
    }
    return facts, view


def game_overview(games: list[Game], game_type: str, track: str, lang: str = "en"):
    game = pick_game(games, track)
    if game is None:
        return no_track(games, game_type, track), None
    won = [leg.number for leg in game.legs if leg.runners[0].finish == "1"]
    facts = [f"{game_type} at {game.track} on {day(game)}: the favourite won {len(won)} of {len(game.legs)} legs"
             + (f" (legs {', '.join(map(str, won))})." if won else ".")]
    rows = []
    for leg in game.legs:
        favourite, winner = leg.runners[0], winner_of(leg)
        line = f"Leg {leg.number}: the favourite {favourite.name} ({favourite.odds:.2f}) {outcome(favourite)}."
        if winner and winner is not favourite:
            line += f" The winner was {winner.name} ({winner.odds:.2f})."
        facts.append(line)
        rows.append({"leg": leg_cell(game, leg), "favourite": runner_cell(favourite), "odds": favourite.odds,
                     "finish": favourite.finish, "winner": runner_cell(winner) if winner else None,
                     "winner_odds": winner.odds if winner else None})
    view = {
        "title": f"{game.track}, {day(game, lang)}",
        "game_type": game_type,
        "columns": [column("leg", say(lang, "Leg"), "leg"), column("favourite", say(lang, "Favourite"), "runner"),
                    column("odds", "V-odds", "odds"), column("finish", say(lang, "Finish"), "finish"),
                    column("winner", say(lang, "Winner"), "runner"), column("winner_odds", "V-odds", "odds")],
        "rows": rows,
    }
    return facts, view


def leg_details(games: list[Game], game_type: str, track: str, number: int, lang: str = "en"):
    game = pick_game(games, track)
    if game is None:
        return no_track(games, game_type, track), None
    leg = next((leg for leg in game.legs if leg.number == number), None)
    if leg is None:
        return [f"Leg {number} does not exist. The {game_type} game at {game.track} on {day(game)} "
                f"has legs 1 to {len(game.legs)}."], None

    favourite, winner = leg.runners[0], winner_of(leg)
    facts = [
        f"Leg {leg.number} of {game_type} at {game.track} on {day(game)}. {len(leg.runners)} horses started.",
        f"The favourite was {favourite.name} at odds {favourite.odds:.2f}, and it {outcome(favourite)}.",
    ]
    if winner and winner is not favourite:
        facts.append(f"The winner was {winner.name} at odds {winner.odds:.2f}.")
    columns = [column("horse", say(lang, "Horse"), "runner"), column("odds", "V-odds", "odds")]
    if favourite.bet_share is not None:
        columns.append(column("share", f"{game_type}%", "percent"))
    columns.append(column("finish", say(lang, "Finish"), "finish"))
    rows = [{"horse": runner_cell(r), "odds": r.odds, "share": (r.bet_share or 0) / 100, "finish": r.finish}
            for r in leg.runners]
    title = say(lang, "Leg {leg}, {track}", leg=leg.number, track=game.track)
    return facts, {"title": title, "game_type": game_type, "columns": columns, "rows": rows}


def upsets(games: list[Game], game_type: str, lang: str = "en"):
    found = [(game, leg, winner) for game in games for leg in game.legs if (winner := winner_of(leg))]
    found.sort(key=lambda item: item[2].odds, reverse=True)
    found = found[:5]
    if not found:
        return [f"No results found in the latest {game_type} games."], None
    facts = [f"The biggest surprise in the latest {game_type} games was {found[0][2].name} winning at odds "
             f"{found[0][2].odds:.2f}."]
    rows = []
    for i, (game, leg, winner) in enumerate(found):
        favourite = leg.runners[0]
        if i < 3:  # fewer facts, fewer mix-ups for a small model. The table shows all five.
            facts.append(f"Leg {leg.number} at {game.track}: the winner was {winner.name} at odds {winner.odds:.2f}. "
                         f"The favourite, {favourite.name} ({favourite.odds:.2f}), {outcome(favourite)}.")
        rows.append({"leg": leg_cell(game, leg), "winner": runner_cell(winner), "odds": winner.odds,
                     "favourite": runner_cell(favourite), "favourite_finish": favourite.finish})
    view = {
        "title": say(lang, "Biggest upsets in {game_type}", game_type=game_type),
        "game_type": game_type,
        "columns": [column("leg", say(lang, "Leg"), "leg"), column("winner", say(lang, "Winner"), "runner"),
                    column("odds", "V-odds", "odds"), column("favourite", say(lang, "Favourite"), "runner"),
                    column("favourite_finish", say(lang, "Fav. finish"), "finish")],
        "rows": rows,
    }
    return facts, view


def bets_vs_odds(games: list[Game], game_type: str, lang: str = "en"):
    legs = [(game, leg) for game in games for leg in game.legs]
    if all(r.bet_share is None for _, leg in legs for r in leg.runners):
        return [f"{game_type} has no V-game pool, so there is no bet share to compare with the odds."], None

    rows, facts = [], []
    odds_wins = crowd_wins = 0
    for game, leg in legs:
        favourite = leg.runners[0]
        crowd = max(leg.runners, key=lambda r: r.bet_share or 0)
        if crowd is favourite:
            continue
        odds_wins += favourite.finish == "1"
        crowd_wins += crowd.finish == "1"
        facts.append(f"Leg {leg.number} at {game.track}: the odds favourite {favourite.name} ({favourite.odds:.2f}) "
                     f"{outcome(favourite)}, the most bet horse {crowd.name} ({crowd.bet_share:.0f}% of bets) {outcome(crowd)}.")
        rows.append({"leg": leg_cell(game, leg), "favourite": runner_cell(favourite), "odds": favourite.odds,
                     "favourite_finish": favourite.finish, "crowd": runner_cell(crowd),
                     "share": crowd.bet_share / 100, "crowd_finish": crowd.finish})
    facts.insert(0, f"In {len(rows)} of {len(legs)} legs the horse with the most {game_type} bets was not the "
                    f"odds favourite. In those legs the odds favourite won {odds_wins} times and the most bet "
                    f"horse won {crowd_wins} times.")
    view = {
        "title": say(lang, "Bets against odds in {game_type}", game_type=game_type),
        "game_type": game_type,
        "columns": [column("leg", say(lang, "Leg"), "leg"), column("favourite", say(lang, "Odds favourite"), "runner"),
                    column("odds", "V-odds", "odds"), column("favourite_finish", say(lang, "Finish"), "finish"),
                    column("crowd", say(lang, "Most bet"), "runner"), column("share", f"{game_type}%", "percent"),
                    column("crowd_finish", say(lang, "Finish"), "finish")],
        "rows": rows,
    }
    return facts, (view if rows else None)


def find_horse(games: list[Game], game_type: str, name: str, lang: str = "en"):
    needle = plain(name)
    if len(needle) < 3:  # "a" would match every other horse
        return ["Ask for the horse with at least 3 letters of its name."], None
    found = [(game, leg, rank, runner) for game in games for leg in game.legs
             for rank, runner in enumerate(leg.runners) if needle in plain(runner.name)]
    if not found:
        return [f"No horse called {name} ran in the latest {game_type} games."], None
    facts = [f"{len(found)} horses matched {name}. These are the first 10."] if len(found) > 10 else []
    rows = []
    for game, leg, rank, runner in found[:10]:
        place = "the favourite (lowest odds)" if rank == 0 else f"number {rank + 1} in the odds (not the favourite)"
        facts.append(f"{runner.name} ran leg {leg.number} of {game_type} at {game.track} on {day(game)} at odds "
                     f"{runner.odds:.2f}, {place}, and {outcome(runner)}.")
        rank_text = say(lang, "Favourite") if rank == 0 else say(lang, "No. {n} in the odds", n=rank + 1)
        rows.append({"leg": leg_cell(game, leg), "horse": runner_cell(runner), "odds": runner.odds,
                     "rank": rank_text, "finish": runner.finish})
    view = {
        "title": say(lang, "{horse} in {game_type}", horse=found[0][3].name, game_type=game_type),
        "game_type": game_type,
        "columns": [column("leg", say(lang, "Leg"), "leg"), column("horse", say(lang, "Horse"), "runner"),
                    column("odds", "V-odds", "odds"), column("rank", say(lang, "Odds rank")),
                    column("finish", say(lang, "Finish"), "finish")],
        "rows": rows,
    }
    return facts, view


# ---------- helpers ----------

def column(key: str, label: str, kind: str = "text") -> dict:
    return {"key": key, "label": label, "type": kind}


def runner_cell(runner: Runner) -> dict:
    return {"number": runner.number, "name": runner.name}


def leg_cell(game: Game, leg: Leg) -> dict:
    return {"leg": leg.number, "track": game.track}


def winner_of(leg: Leg) -> Runner | None:
    return next((r for r in leg.runners if r.finish == "1"), None)


def pick_game(games: list[Game], track: str) -> Game | None:
    """The game at the named track, or the latest game when no track is given."""
    if not plain(track):
        return games[0]
    return next((game for game in games if plain(track) in plain(game.track)), None)


def no_track(games: list[Game], game_type: str, track: str) -> list[str]:
    tracks = ", ".join(f"{game.track} ({day(game)})" for game in games)
    return [f"None of the latest {game_type} games were at {track}. They were at: {tracks}."]


def plain(text: str) -> str:
    """Lowercase letters and digits only, without accents: "Åby" -> "aby", "Frank S.H." -> "franksh"."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(c for c in ascii_text.lower() if c.isalnum())


def outcome(runner: Runner) -> str:
    if runner.finish == "1":
        return "won"
    if runner.finish == "disqualified":
        return "was disqualified"
    if runner.finish == "unplaced":
        return "finished outside the top 3"
    return f"finished {ordinal(int(runner.finish))}"


def day(game: Game, lang: str = "en") -> str:
    return words.day(game.start, lang)


def median_text(summary: dict, lang: str = "en") -> str:
    return ordinal(summary["median"], lang) + ("" if summary["median_exact"] else say(lang, " or worse"))


def percent(x: float) -> str:
    return f"{round(x * 100)}%"
