import json

import httpx
import pytest

from app import ask

BODEN = "V85_2026-10-03_11_5"


def test_odds_question_never_shows_results(load):
    leg1 = load(BODEN, True).legs[0]
    prompt, schema = ask.odds_question(leg1)
    for word in ("Position", "Disqualified", "won", "finish"):
        assert word not in prompt
    assert prompt.index("R.K.Kiara") < prompt.index("Arizona")  # sorted by odds
    names = schema["properties"]["favourites"]["items"]["enum"]
    assert names == [r.name for r in leg1.runners]  # only horses from this leg


def test_result_question_layout(load):
    leg1 = load(BODEN, True).legs[0]
    prompt, schema = ask.result_question(leg1, "R.K.Kiara")
    assert "Position 1: R.K.Kiara" in prompt
    assert "Disqualified: Arizona" in prompt
    assert "In which position did R.K.Kiara finish?" in prompt
    labels = schema["properties"]["position"]["enum"]
    assert labels[0] == "1" and labels[-1] == "disqualified"


@pytest.mark.anyio
async def test_ask_leg_uses_the_favourite_from_step_a(load):
    leg1 = load(BODEN, True).legs[0]
    prompts = []

    def fake_llm(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompts.append(body["messages"][0]["content"])
        if "favourites" in body["response_format"]["json_schema"]["schema"]["properties"]:
            answer = {"favourites": ["Arizona", "R.K.Kiara", "Sonoma L.A."]}  # wrong on purpose
        else:
            answer = {"position": "disqualified", "won": False}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(fake_llm)) as client:
        result = await ask.ask_leg(client, leg1)

    assert "In which position did Arizona finish?" in prompts[1]
    assert result == {"favourites": ["Arizona", "R.K.Kiara", "Sonoma L.A."], "position": "disqualified", "won": False}
