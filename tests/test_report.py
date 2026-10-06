import pytest

import statistics

from app import ask, check, fetch, report
from conftest import raw

GAMES = ["V85_2026-10-03_11_5", "V85_2026-09-27_5_5"]


@pytest.fixture(autouse=True)
def fake_atg(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "CACHE", tmp_path)

    async def recent_games(client, game_type):
        return [raw(g) for g in GAMES]
    monkeypatch.setattr(fetch, "recent_games", recent_games)

    async def honest_summary(client, rows, mode="local"):  # counts exactly what its per-leg answers say
        return {"wins": sum(place == 1 for _, _, place in rows), "median": statistics.median(p for _, _, p in rows)}
    monkeypatch.setattr(ask, "ask_summary", honest_summary)


async def run(game_type="V85", use_cache=True, mode="local"):
    return [event async for event in report.report(game_type, use_cache, mode)]


@pytest.mark.anyio
async def test_perfect_model_passes_every_check(monkeypatch):
    async def perfect(client, leg, mode="local"):
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
    async def always_says_won(client, leg, mode="local"):
        return {**check.leg_answer(leg), "position": "1", "won": True}
    monkeypatch.setattr(ask, "ask_leg", always_says_won)

    events = await run()
    wrong = [e for e in events if e["type"] == "leg" and not e["checks"]["won"]]
    assert len(wrong) == 16 - 7  # every leg the favourite did not win
    assert events[-1]["checks"] == {"wins": False, "median": False}


@pytest.mark.anyio
async def test_answers_are_reused_for_finished_games(monkeypatch):
    calls = []

    async def counting(client, leg, mode="local"):
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


@pytest.mark.anyio
async def test_local_mode_counts_with_code_and_claude_mode_asks_the_model(monkeypatch):
    async def perfect(client, leg, mode="local"):
        return check.leg_answer(leg)
    monkeypatch.setattr(ask, "ask_leg", perfect)
    summaries = []

    async def summary(client, rows, mode="local"):
        summaries.append(len(rows))
        return {"wins": 6, "median": 2.0}  # one win short, on purpose
    monkeypatch.setattr(ask, "ask_summary", summary)

    async def claude_name(mode):
        return "claude-test" if mode == "claude" else ask.MODEL
    monkeypatch.setattr(ask, "model_name", claude_name)

    local = (await run())[-1]
    assert local["summed_up_by"] == "code" and local["llm"]["wins"] == 7 and summaries == []
    claude = (await run(mode="claude"))[-1]
    assert claude["summed_up_by"] == "model" and summaries == [16]
    assert claude["llm"]["wins"] == 6 and claude["checks"] == {"wins": False, "median": True}
    await run(mode="claude")
    assert summaries == [16]  # the summary is saved too
