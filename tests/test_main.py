"""The web API: the error codes the page turns into text, and the request limits."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import ask, claude, main

client = TestClient(main.app)  # without "with", so the start-up announcer does not run


def fails_with(error):
    async def report(game_type, mode="local"):
        yield {"type": "games", "game_type": game_type}
        raise error
    return report


@pytest.mark.parametrize("error, code", [
    (httpx.ConnectError("refused", request=httpx.Request("POST", ask.LLM_URL + "/v1/chat/completions")), "model_not_ready"),
    (httpx.ConnectError("refused", request=httpx.Request("GET", "https://www.atg.se/services/racinginfo/v1/api/games/x")), "atg_unavailable"),
    (claude.Unavailable("no key"), "claude_unavailable"),
    (ValueError("a bug"), "failed"),
])
def test_each_failure_has_its_own_code(monkeypatch, error, code):
    monkeypatch.setattr(main, "report", fails_with(error))
    lines = client.get("/api/report/V85").text.strip().splitlines()
    assert json.loads(lines[0])["type"] == "games"  # what came before the failure still arrives
    assert json.loads(lines[-1])["code"] == code


def test_requests_are_limited():
    too_long = {"messages": [{"role": "user", "content": "x" * 4001}], "game_type": "V85"}
    assert client.post("/api/chat", json=too_long).status_code == 422
    assert client.get("/api/report/NOTAGAMETYPE").status_code == 422
    assert client.get("/api/report/V85?mode=gpt").status_code == 422
