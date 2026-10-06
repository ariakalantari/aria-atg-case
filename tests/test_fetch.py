import httpx
import pytest

from app import fetch
from conftest import raw

UNFINISHED = "trio_2026-10-05_67_2"
FINISHED = ["V85_2026-10-03_11_5", "V85_2026-09-27_5_5", "dd_2026-10-04_14_9"]


def fake_atg(results: list[str], calls: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        name = request.url.path.rsplit("/", 1)[-1]
        if "/products/" in request.url.path:
            return httpx.Response(200, json={"betType": name, "results": [{"id": i} for i in results]})
        return httpx.Response(200, json=raw(name))
    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def temp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "CACHE", tmp_path)


@pytest.mark.anyio
async def test_skips_games_that_are_not_finished():
    calls = []
    async with httpx.AsyncClient(transport=fake_atg([UNFINISHED, *FINISHED], calls)) as client:
        games = await fetch.recent_games(client, "V85")
    assert [g["id"] for g in games] == FINISHED


@pytest.mark.anyio
async def test_finished_games_are_fetched_once():
    calls = []
    async with httpx.AsyncClient(transport=fake_atg(FINISHED, calls)) as client:
        await fetch.recent_games(client, "V85")
        await fetch.recent_games(client, "V85")
    game_calls = [c for c in calls if "/games/" in c]
    assert len(game_calls) == 3  # the second run reads them from disk


@pytest.mark.anyio
async def test_game_type_without_games():
    # V75 was replaced by V85, ATG returns only {"betType": "V75"}
    def handler(request):
        return httpx.Response(200, json={"betType": "V75"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch.recent_games(client, "V75") == []


@pytest.mark.anyio
async def test_unknown_game_type():
    def handler(request):
        return httpx.Response(404, json={})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch.recent_games(client, "v85") == []
