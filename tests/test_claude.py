"""Claude mode, against a fake Foundry server (no key needed, nothing is spent)."""
import json

import anthropic
import httpx2 as httpx  # the Anthropic SDK has its own copy of httpx
import pytest

from app import agent, claude

TEXT = {"id": "msg_1", "type": "message", "role": "assistant", "model": "m", "stop_reason": "end_turn",
        "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 5}}


@pytest.fixture
def foundry(monkeypatch):
    """A fake Foundry resource. Set .reply (a function of the request body) to answer; .asked keeps the bodies."""
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "test-resource")
    fake = type("Fake", (), {"asked": [], "reply": None})()

    def handle(request):
        body = json.loads(request.content)
        fake.asked.append(body)
        return fake.reply(body)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(claude, "_client", anthropic.AsyncAnthropicFoundry(http_client=http))
    monkeypatch.setattr(claude, "_model", None)
    return fake


def message(text: str) -> httpx.Response:
    return httpx.Response(200, json={**TEXT, "content": [{"type": "text", "text": text}]})


def events(*items: dict) -> httpx.Response:
    lines = "".join(f"event: {item['type']}\ndata: {json.dumps(item)}\n\n" for item in items)
    return httpx.Response(200, text=lines, headers={"content-type": "text/event-stream"})


@pytest.mark.anyio
async def test_picks_the_newest_sonnet_that_is_deployed(foundry):
    deployed = {"claude-sonnet-5", "claude-sonnet-4-6"}
    foundry.reply = lambda body: message("Hi") if body["model"] in deployed else httpx.Response(
        404, json={"type": "error", "error": {"type": "not_found_error", "message": "DeploymentNotFound"}})
    assert await claude.model() == "claude-sonnet-5"
    assert await claude.model() == "claude-sonnet-5"
    assert [body["model"] for body in foundry.asked] == ["claude-sonnet-5-5", "claude-sonnet-5"]  # found once


@pytest.mark.anyio
async def test_ask_sends_a_strict_schema_and_reads_the_json(foundry, monkeypatch):
    monkeypatch.setattr(claude, "_model", "claude-sonnet-4-6")
    foundry.reply = lambda body: message('{"favourites": ["A", "B", "C"]}')
    names = {"type": "string", "enum": ["A", "B", "C", "D"]}
    schema = {"type": "object", "properties": {"favourites": {"type": "array", "items": names, "minItems": 3, "maxItems": 3}},
              "required": ["favourites"]}
    assert await claude.ask("Who are the favourites?", schema) == {"favourites": ["A", "B", "C"]}
    sent = foundry.asked[0]["output_config"]["format"]["schema"]
    assert sent["additionalProperties"] is False
    assert sent["properties"]["favourites"] == {"type": "array", "items": names}


def test_no_key_means_unavailable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_FOUNDRY_API_KEY", raising=False)
    assert not claude.configured()
    with pytest.raises(claude.Unavailable):
        claude.client()


def test_conversation_in_claude_format():
    conversation = [
        {"role": "system", "content": "You are Harry."},
        {"role": "user", "content": "Biggest upset?"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_0", "type": "function", "function": {"name": "upsets", "arguments": '{"game_type": "V85"}'}},
            {"id": "call_1", "type": "function", "function": {"name": "favourite_stats", "arguments": ""}}]},
        {"role": "tool", "tool_call_id": "call_0", "content": "Leg 4 at Åby"},
        {"role": "tool", "tool_call_id": "call_1", "content": "10 of 24"},
        {"role": "assistant", "content": "Wiener Sängerknabe."},
    ]
    system, messages = claude.to_claude(conversation)
    assert system == "You are Harry."
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[1]["content"][0] == {"type": "tool_use", "id": "call_0", "name": "upsets", "input": {"game_type": "V85"}}
    assert messages[1]["content"][1]["input"] == {}
    assert [block["tool_use_id"] for block in messages[2]["content"]] == ["call_0", "call_1"]  # both results in one turn


@pytest.mark.anyio
async def test_stream_gives_text_and_whole_tool_calls(foundry, monkeypatch):
    monkeypatch.setattr(claude, "_model", "claude-sonnet-4-6")
    foundry.reply = lambda body: events(
        {"type": "message_start", "message": {**TEXT, "content": [], "stop_reason": None}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Let me look."}},
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "leg_details", "input": {}}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"leg": 7}'}},
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"output_tokens": 9}},
        {"type": "message_stop"},
    )
    tool = {"type": "function", "function": {"name": "leg_details", "description": "One leg", "parameters": {"type": "object"}}}
    pieces = [piece async for piece in claude.stream([{"role": "user", "content": "Leg 7?"}], [tool])]
    assert pieces[0] == ("text", "Let me look.")
    assert pieces[-1] == ("tool", {"index": 0, "id": "toolu_1", "function": {"name": "leg_details", "arguments": '{"leg": 7}'}})
    assert foundry.asked[0]["tools"] == [{"name": "leg_details", "description": "One leg", "input_schema": {"type": "object"}}]


@pytest.mark.anyio
async def test_harry_runs_on_claude_in_claude_mode(monkeypatch):
    seen = []

    async def fake_model():
        return "claude-sonnet-5-5"

    async def fake_stream(conversation, tool_schemas):
        seen.append(conversation[0]["content"])
        yield "text", "Hej!"

    async def no_games(client, game_type):
        return []

    monkeypatch.setattr(claude, "model", fake_model)
    monkeypatch.setattr(claude, "stream", fake_stream)
    monkeypatch.setattr(agent.tools, "load", no_games)
    events_out = [e async for e in agent.chat([{"role": "user", "content": "Hej"}], "V85", "sv", "claude")]
    assert [e["type"] for e in events_out][:2] == ["token", "done"]
    assert "You run on Claude Sonnet 5.5 by Anthropic" in seen[0]


def test_azure_names_and_any_endpoint_form(monkeypatch):
    for name in ("ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_RESOURCE", "ANTHROPIC_FOUNDRY_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AZURE_ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("AZURE_ANTHROPIC_ENDPOINT", "https://my-res.services.ai.azure.com/anthropic/v1/messages")
    assert claude.configured()
    assert claude.base_url() == "https://my-res.services.ai.azure.com/anthropic/"
