"""Step 5: the whole pipeline for one game type, as a stream of small events.

fetch -> clean -> the LLM answers each leg -> check with code -> sum up -> check with code

Summing up (how often the favourite won, its median finish): in Claude mode the LLM does it from its own
per-leg answers. The local 2B model cannot count a 24-line list (measured: it said 1 win where its own
answers had 11, sorted or not), so in Local mode code counts the 2B model's per-leg answers instead.

The page shows each leg as soon as its event arrives. The model's answers are saved per
finished game, so a second look at the same games is instant.

It also runs from the command line, for example: python -m app.report V86 (add --claude for Claude mode)
"""
import asyncio
import json
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path

import httpx

from . import ask, check, clean, fetch
from .words import ordinal


async def report(game_type: str, use_cache: bool = True, mode: str = "local"):
    game_type = next((known for known in fetch.GAME_TYPES if known.lower() == game_type.lower()), game_type)
    model = await ask.model_name(mode)
    async with httpx.AsyncClient(timeout=30) as client:
        raw_games = await fetch.recent_games(client, game_type)
        if not raw_games:
            yield {"type": "error", "code": "no_games", "message": f"ATG has no finished {game_type} games right now."}
            return

        games = [clean.parse_game(raw) for raw in raw_games]
        yield {
            "type": "games",
            "game_type": game_type,
            "model": ask.display(model),
            "games": [{"id": g.id, "track": g.track, "start": g.start, "legs": len(g.legs)} for g in games],
        }

        # One folder per model. v2: the model also gives the V-odds and sums up.
        folder = fetch.CACHE / "answers" / "v2" / re.sub(r"[^A-Za-z0-9.-]+", "_", model)
        answers, rows, true_answers, legs = [], [], [], []
        total_seconds, fresh = 0.0, False
        for game in games:
            path = folder / f"{game.id}.json"
            saved = load(path) if use_cache else {}
            for leg in game.legs:
                key = str(leg.number)
                cached = key in saved
                started = time.monotonic()
                if not cached:
                    saved[key] = await ask.ask_leg(client, leg, mode)
                    save(path, saved)  # at once, so a report stopped halfway keeps its answers
                    fresh = True
                seconds = time.monotonic() - started
                total_seconds += seconds

                answer, truth = saved[key], check.leg_answer(leg)
                answers.append(answer)
                rows.append((f"{game.track} leg {leg.number}", answer["position"], check.position(answer["position"], leg)[0]))
                true_answers.append(truth)
                legs.append(leg)
                yield leg_event(game, leg, answer, truth, seconds, cached)

        truth = check.summary(list(zip(true_answers, legs)))
        if mode == "claude":  # Claude sums up its own per-leg answers
            path = folder / f"summary_{'+'.join(g.id for g in games)}.json"
            stated = load(path) if use_cache and not fresh else {}
            if not stated:
                started = time.monotonic()
                stated = await ask.ask_summary(client, rows, mode)
                total_seconds += time.monotonic() - started
                save(path, stated)
            llm = {**truth, "wins": stated["wins"], "win_rate": stated["wins"] / len(legs), "median": stated["median"]}
        else:  # code counts the small model's own per-leg answers
            llm = check.summary(list(zip(answers, legs)))
        yield {
            "type": "summary",
            "llm": llm,
            "truth": truth,
            "checks": {"wins": llm["wins"] == truth["wins"], "median": llm["median"] == truth["median"]},
            "odds_win_rate": check.odds_win_rate(legs),
            "seconds": round(total_seconds, 1),
            "summed_up_by": "model" if mode == "claude" else "code",
        }


def leg_event(game: clean.Game, leg: clean.Leg, answer: dict, truth: dict, seconds: float, cached: bool) -> dict:
    return {
        "type": "leg",
        "game": game.id,
        "leg": leg.number,
        "runners": [asdict(r) for r in leg.runners],  # lowest odds first
        "llm": answer,
        "truth": truth,
        "checks": check.compare(answer, truth),
        "seconds": round(seconds, 1),
        "cached": cached,
        # Exactly what the model was shown, for the "what the model saw" panel
        "prompts": [ask.odds_question(leg)[0], ask.result_question(leg, answer["favourites"][0])[0]],
    }


def load(path: Path) -> dict:
    """Saved answers, or none if there are none yet (or the file was cut off)."""
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def save(path: Path, answers: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(answers))


async def main(game_type: str, mode: str) -> None:
    """The four answers for one game type, as a table, with the code's check next to each."""
    tracks = {}
    async for event in report(game_type, mode=mode):
        if event["type"] == "error":
            print(event["message"])
        elif event["type"] == "games":
            tracks = {g["id"]: g["track"] for g in event["games"]}
            print(f"{event['game_type']}, the three latest games, answered by {event['model']}\n")
            print(f"{'Leg':<16}{'The three favourites, with V-odds':<66}{'Favourite':<14}Check")
        elif event["type"] == "leg":
            llm = event["llm"]
            picks = ", ".join(f"{name} {odds:.2f}" for name, odds in zip(llm["favourites"], llm["odds"]))
            finish = "won" if llm["won"] else llm["position"]
            print(f"{tracks[event['game']] + ' ' + str(event['leg']):<16}{picks:<66}{finish:<14}"
                  f"{'right' if all(event['checks'].values()) else 'wrong'}")
        elif event["type"] == "summary":
            llm, truth, checks = event["llm"], event["truth"], event["checks"]
            wins = "right" if checks["wins"] else f"wrong, code counted {truth['wins']}"
            median = "right" if checks["median"] else f"wrong, code got {ordinal(truth['median'])}"
            print(f"\nThe favourite won {llm['wins']} of {llm['legs']} legs, {llm['win_rate']:.0%} ({wins})")
            print(f"Median finishing position: {ordinal(llm['median'])} ({median})")
            print(f"The odds gave the favourite a {event['odds_win_rate']:.0%} chance on average")
            if event["summed_up_by"] == "code":
                print("(Win count and median counted by code from the model's own per-leg answers.)")


if __name__ == "__main__":
    args = sys.argv[1:]
    asyncio.run(main(next((a for a in args if a != "--claude"), "V85"), "claude" if "--claude" in args else "local"))
