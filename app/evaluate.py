"""Measure how often the model is right, over many legs and game types.

It runs the same pipeline as the page, with fresh answers (no cache), and adds up
the checks. Run it inside the app container, for example:

    docker compose exec app python -m app.evaluate
    docker compose exec app python -m app.evaluate V85 V86 dd
    docker compose exec app python -m app.evaluate --claude     (Claude mode, needs the key in .env)
"""
import asyncio
import sys
from collections import Counter

from . import claude
from .fetch import GAME_TYPES
from .report import report


async def main(game_types: list[str], mode: str = "local") -> None:
    right, total = Counter(), Counter()
    seconds, model = 0.0, ""
    for game_type in game_types:
        legs_right = legs = 0
        async for event in report(game_type, use_cache=False, mode=mode):
            if event["type"] == "games":
                model = event["model"]
                print(f"{game_type:>5}: games {', '.join(g['id'] for g in event['games'])}", flush=True)
            elif event["type"] == "leg":
                seconds += event["seconds"]
                legs += 1
                legs_right += all(event["checks"].values())
                for name, ok in event["checks"].items():
                    right[name] += ok
                    total[name] += 1
            elif event["type"] == "summary":
                for name, ok in event["checks"].items():
                    right[f"summary {name}"] += ok
                    total[f"summary {name}"] += 1
            elif event["type"] == "error":
                print(f"{game_type}: {event['message']}")
        print(f"{game_type:>5}: {legs_right}/{legs} legs fully right", flush=True)

    legs = total["favourites"]
    print(f"\nModel: {model}")
    print(f"Legs: {legs}, model time: {seconds:.0f} s ({seconds / max(legs, 1):.1f} s per leg)")
    for name in total:
        print(f"  {name:<16} {right[name]:>4}/{total[name]:<4} {right[name] / total[name]:.0%}")
    if mode == "claude":
        print(f"Tokens: {claude.USAGE['input']} in, {claude.USAGE['output']} out")


if __name__ == "__main__":
    args = sys.argv[1:]
    mode = "claude" if "--claude" in args else "local"
    asyncio.run(main([a for a in args if a != "--claude"] or GAME_TYPES, mode))
