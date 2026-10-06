"""Step 5: the whole pipeline for one game type, as a stream of small events.

fetch -> clean -> ask the LLM, leg by leg -> check with code -> summary

The page shows each leg as soon as its event arrives. The model's answers are
saved per finished game, so a second look at the same games is instant.
"""
import json
import re
import time
from dataclasses import asdict

import httpx

from . import ask, check, clean, fetch


async def report(game_type: str, use_cache: bool = True):
    async with httpx.AsyncClient(timeout=30) as client:
        raw_games = await fetch.recent_games(client, game_type)
        if not raw_games:
            yield {"type": "error", "code": "no_games", "message": f"ATG has no finished {game_type} games right now."}
            return

        games = [clean.parse_game(raw) for raw in raw_games]
        yield {
            "type": "games",
            "game_type": game_type,
            "model": ask.MODEL,
            "games": [{"id": g.id, "track": g.track, "start": g.start, "legs": len(g.legs)} for g in games],
        }

        llm_answers, true_answers, legs = [], [], []
        total_seconds = 0.0
        for game in games:
            path = answers_file(game.id)
            saved = json.loads(path.read_text()) if use_cache and path.exists() else {}
            for leg in game.legs:
                key = str(leg.number)
                cached = key in saved
                started = time.monotonic()
                if not cached:
                    saved[key] = await ask.ask_leg(client, leg)
                seconds = time.monotonic() - started
                total_seconds += seconds

                answer, truth = saved[key], check.leg_answer(leg)
                llm_answers.append(answer)
                true_answers.append(truth)
                legs.append(leg)
                yield leg_event(game, leg, answer, truth, seconds, cached)

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(saved))

        # The summary numbers are counted by code from the model's own per-leg answers.
        # Small models miscount long lists, so we do not ask them to count.
        llm = check.summary(list(zip(llm_answers, legs)))
        truth = check.summary(list(zip(true_answers, legs)))
        yield {
            "type": "summary",
            "llm": llm,
            "truth": truth,
            "checks": {key: llm[key] == truth[key] for key in ("wins", "median")},
            "odds_win_rate": check.odds_win_rate(legs),
            "seconds": round(total_seconds, 1),
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


def answers_file(game_id: str):
    model = re.sub(r"[^A-Za-z0-9.-]+", "_", ask.MODEL)
    return fetch.CACHE / "answers" / model / f"{game_id}.json"
