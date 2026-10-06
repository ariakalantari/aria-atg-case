"""Step 1: fetch games from ATG's racing API.

Finished games never change, so they are saved to disk and only fetched once.
"""
import asyncio
import json
import os
from pathlib import Path

import httpx

API = "https://www.atg.se/services/racinginfo/v1/api"
CACHE = Path(os.getenv("CACHE_DIR", "cache"))
GAME_TYPES = ["V85", "V86", "GS75", "V64", "V65", "V5", "V4", "V3", "dd", "ld"]


async def recent_games(client: httpx.AsyncClient, game_type: str, count: int = 3) -> list[dict]:
    """The `count` most recent finished games for a game type, newest first."""
    response = await client.get(f"{API}/products/{game_type}")
    if response.status_code == 404:  # unknown game type (they are case sensitive: "v85" is unknown)
        return []
    response.raise_for_status()
    ids = [game["id"] for game in response.json().get("results", [])]

    # Fetch the first few in parallel. The list can include a game that has not
    # finished yet, so keep going down the list until we have enough.
    games = await asyncio.gather(*(get_game(client, game_id) for game_id in ids[:count]))
    finished = [game for game in games if game["status"] == "results"]
    for game_id in ids[count:]:
        if len(finished) == count:
            break
        game = await get_game(client, game_id)
        if game["status"] == "results":
            finished.append(game)
    return finished


async def get_game(client: httpx.AsyncClient, game_id: str) -> dict:
    path = CACHE / "games" / f"{game_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    response = await client.get(f"{API}/games/{game_id}")
    response.raise_for_status()
    game = response.json()
    if game["status"] == "results":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(game), encoding="utf-8")
    return game
