import pytest

from app import ask, check, fetch, report
from conftest import raw

GAMES = ["V85_2026-10-03_11_5", "V85_2026-09-27_5_5"]


@pytest.fixture(autouse=True)
def fake_atg(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "CACHE", tmp_path)

    async def recent_games(client, game_type):
        return [raw(g) for g in GAMES]
    monkeypatch.setattr(fetch, "recent_games", recent_games)


async def run(game_type="V85", use_cache=True):
    return [event async for event in report.report(game_type, use_cache)]


@pytest.mark.anyio
async def test_perfect_model_passes_every_check(monkeypatch):
    async def perfect(client, leg):
        return check.leg_answer(leg)
    monkeypatch.setattr(ask, "ask_leg", perfect)

    events = await run()
    legs = [e for e in events if e["type"] == "leg"]
    summary = events[-1]
    assert events[0]["type"] == "games" and len(events[0]["games"]) == 2
    assert len(legs) == 16
    assert all(all(e["checks"].values()) for e in legs)
    assert summary["type"] == "summary" and all(summary["checks"].values())
    assert summary["llm"]["wins"] == 7


@pytest.mark.anyio
async def test_wrong_answers_are_caught(monkeypatch):
    async def always_says_won(client, leg):
        return {**check.leg_answer(leg), "position": "1", "won": True}
    monkeypatch.setattr(ask, "ask_leg", always_says_won)

    events = await run()
    wrong = [e for e in events if e["type"] == "leg" and not e["checks"]["won"]]
    assert len(wrong) == 16 - 7  # every leg the favourite did not win
    assert events[-1]["checks"] == {"wins": False, "median": False}


@pytest.mark.anyio
async def test_answers_are_reused_for_finished_games(monkeypatch):
    calls = []

    async def counting(client, leg):
        calls.append(leg.number)
        return check.leg_answer(leg)
    monkeypatch.setattr(ask, "ask_leg", counting)

    await run()
    events = await run()
    assert len(calls) == 16  # the second run asked the model nothing
    assert all(e["cached"] for e in events if e["type"] == "leg")


@pytest.mark.anyio
async def test_no_games_gives_a_friendly_error(monkeypatch):
    async def none(client, game_type):
        return []
    monkeypatch.setattr(fetch, "recent_games", none)
    assert await run("V75") == [
        {"type": "error", "code": "no_games", "message": "ATG has no finished V75 games right now."}]
