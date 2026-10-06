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
    favourite = schema["properties"]["favourites"]["items"]["properties"]
    assert favourite["name"]["enum"] == [r.name for r in leg1.runners]  # only horses from this leg
    assert favourite["odds"]["enum"][0] == f"{leg1.runners[0].odds:.2f}"  # and only their odds


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
            answer = {"favourites": [{"name": "Arizona", "odds": "4.20"}, {"name": "R.K.Kiara", "odds": "1.35"},
                                     {"name": "Sonoma L.A.", "odds": "6.04"}]}  # wrong on purpose
        else:
            answer = {"position": "disqualified", "won": False}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(fake_llm)) as client:
        result = await ask.ask_leg(client, leg1)

    assert "In which position did Arizona finish?" in prompts[1]
    assert result == {"favourites": ["Arizona", "R.K.Kiara", "Sonoma L.A."], "odds": [4.2, 1.35, 6.04],
                      "position": "disqualified", "won": False}


def test_summary_question_lists_the_models_own_answers():
    prompt, schema = ask.summary_question([("Boden leg 1", "1", 1), ("Boden leg 2", "disqualified", 12),
                                           ("Bjerke leg 3", "unplaced", 4)])
    assert "- Boden leg 1: 1st, won" in prompt
    assert "- Boden leg 2: disqualified, counts as last (12th)" in prompt
    assert "- Bjerke leg 3: outside the top 3, counts as 4th" in prompt
    assert schema["properties"]["wins"]["maximum"] == 3


def test_model_names_for_people():
    assert ask.display("unsloth/Qwen3.5-2B-GGUF:Q4_K_M") == "Qwen 3.5 2B"
    assert ask.display("claude-sonnet-5-5") == "Claude Sonnet 5.5"
    assert ask.display("my-sonnet-4-6") == "Claude Sonnet 4.6"  # a custom deployment name
