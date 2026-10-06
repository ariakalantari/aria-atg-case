"""Shared test helpers. The fixtures are real ATG games, trimmed to the fields we use."""
import json
from pathlib import Path

import pytest

from app import clean

FIXTURES = Path(__file__).parent / "fixtures"


def raw(game_id: str) -> dict:
    return json.loads((FIXTURES / f"{game_id}.json").read_text(encoding="utf-8"))


@pytest.fixture
def load():
    """load("V85_...") gives the raw game, load("V85_...", True) the parsed Game."""
    return lambda game_id, clean_it=False: clean.parse_game(raw(game_id)) if clean_it else raw(game_id)


@pytest.fixture
def anyio_backend():
    return "asyncio"
