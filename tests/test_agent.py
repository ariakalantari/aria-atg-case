import json

import httpx
import pytest

from app import agent, tools

BODEN = "V85_2026-10-03_11_5"

LEG_7_CALL = [  # a tool call arrives in pieces, like llama.cpp streams it
    {"tool_calls": [{"index": 0, "id": "abc", "function": {"name": "leg_details", "arguments": ""}}]},
    {"tool_calls": [{"index": 0, "function": {"arguments": '{"game_type": "V85", '}}]},
    {"tool_calls": [{"index": 0, "function": {"arguments": '"leg": 7, "track": "Boden"}'}}]},
]
ANSWER = [{"content": "Shogun R.R. was the favourite "}, {"content": "but Frank S.H. won."}]
FOLLOW_UPS = {"picks": ["Show all legs at Boden", "Show leg 8 at Boden"], "question": "Who won leg 5 at Boden?"}


follow_up_requests = []


def sse(deltas: list[dict]) -> str:
    """A streamed reply in the format llama.cpp (and OpenAI) use."""
    lines = [f"data: {json.dumps({'choices': [{'delta': delta}]})}" for delta in deltas]
    return "\n\n".join([*lines, "data: [DONE]"]) + "\n\n"


@pytest.fixture
def fake_model(load, monkeypatch):
    """Returns a function that sets the fake model's replies, one per request. Records the requests.
    The follow-up call (the one with a JSON schema) always gets FOLLOW_UPS and is recorded in follow_up_requests."""
    requests, replies = [], []
    follow_up_requests.clear()

    async def fake_load(client, game_type):
        return [load(BODEN, True)]
    monkeypatch.setattr(tools, "load", fake_load)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "response_format" in body:
            follow_up_requests.append(body)
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(FOLLOW_UPS)}}]})
        requests.append(body)
        return httpx.Response(200, text=sse(replies[min(len(requests), len(replies)) - 1]))

    real_client = httpx.AsyncClient
    monkeypatch.setattr(agent.httpx, "AsyncClient",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))

    def set_replies(*new_replies):
        replies.extend(new_replies)
        return requests
    return set_replies


async def run(question: str, lang: str = "en") -> list[dict]:
    return [event async for event in agent.chat([{"role": "user", "content": question}], "V85", lang)]


def without_status(events: list[dict]) -> list[dict]:
    return [event for event in events if event["type"] != "status"]


def call(name: str, arguments: str) -> list[dict]:
    """A whole tool call in one piece."""
    return [{"tool_calls": [{"index": 0, "id": "xyz", "function": {"name": name, "arguments": arguments}}]}]


@pytest.mark.anyio
async def test_tool_call_then_answer(fake_model):
    requests = fake_model(LEG_7_CALL, ANSWER)
    tool, *tokens, done, follow_ups = without_status(await run("Show me leg 7 at Boden"))

    assert tool["type"] == "tool" and tool["label"] == "Looked up leg 7 at Boden"
    assert tool["view"]["title"] == "Leg 7, Boden"
    assert "".join(t["text"] for t in tokens) == "Shogun R.R. was the favourite but Frank S.H. won."
    assert done["type"] == "done"
    assert done["calls"][0]["name"] == "leg_details"
    assert done["calls"][0]["arguments"] == {"game_type": "V85", "leg": 7, "track": "Boden"}
    assert "The winner was Frank S.H. at odds 2.49." in done["calls"][0]["facts"]

    # The second request carries the tool call and the tool's facts back to the model
    second = requests[1]["messages"]
    assert second[-2]["tool_calls"][0]["function"]["name"] == "leg_details"
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "abc"
    assert "The winner was Frank S.H. at odds 2.49." in second[-1]["content"]


@pytest.mark.anyio
async def test_plain_chat_needs_no_tools(fake_model):
    fake_model([{"content": "Hi! I can tell you how the favourites did."}])
    events = await run("Hi!")
    assert [e["type"] for e in events] == ["status", "token", "done", "followups"]
    assert events[-1]["questions"] == ["Summarise V85", "Biggest upsets in V85", "Compare all game types"]
    assert not follow_up_requests  # no race data looked up, so preset ideas and no extra model call


@pytest.mark.anyio
async def test_the_page_is_described_next_to_the_question(fake_model):
    requests = fake_model(LEG_7_CALL, ANSWER)
    await run("Show me leg 7 at Boden")
    first = requests[0]["messages"]
    assert first[0]["role"] == "system"
    assert first[-1]["content"] == (
        "(The page shows V85. Its latest games: Boden on Saturday 3 October. Answer in English.)\n\nShow me leg 7 at Boden")


@pytest.mark.anyio
async def test_follow_ups_come_after_done(fake_model):
    fake_model(LEG_7_CALL, ANSWER)
    events = await run("Show me leg 7 at Boden")
    assert [e["type"] for e in events][-2:] == ["done", "followups"]
    assert events[-1]["questions"] == ["Show all legs at Boden", "Show leg 8 at Boden", "Who won leg 5 at Boden?"]

    # The model only chooses among preset ideas built from the leg it just looked up
    ideas = follow_up_requests[0]["response_format"]["json_schema"]["schema"]["properties"]["picks"]["items"]["enum"]
    assert ideas[:3] == ["Show leg 8 at Boden", "Show all legs at Boden", "Biggest upsets in V85"]
    assert "Shogun R.R. was the favourite but Frank S.H. won." in follow_up_requests[0]["messages"][0]["content"]


@pytest.mark.anyio
async def test_follow_ups_follow_the_question_language(fake_model):
    fake_model([{"content": "Hej! Fråga mig om favoriterna."}])
    events = [event async for event in agent.chat([{"role": "user", "content": "Hej!"}], "V85", "en")]
    assert events[-1]["questions"][0] == "Sammanfatta V85"


def test_answer_language_follows_the_question_then_the_page():
    assert agent.answer_language("What was the biggest upset?", "sv") == "en"
    assert agent.answer_language("Vilken var den största skrällen?", "en") == "sv"
    assert agent.answer_language("Hej!", "en") == "sv"
    assert agent.answer_language("V85?", "sv") == "sv"  # unclear: the page decides
    assert agent.answer_language("V85?", "en") == "en"


@pytest.mark.anyio
async def test_gives_up_politely_after_too_many_tool_rounds(fake_model):
    requests = fake_model(LEG_7_CALL)  # the model asks for tools every time
    events = await run("Show me leg 7 at Boden")
    assert len(requests) == agent.MAX_ROUNDS
    assert events[-3]["text"].startswith("I could not finish that one.")
    assert [e["type"] for e in events][-3:] == ["token", "done", "followups"]
    assert sum(e.get("state") == "thinking" for e in events) == agent.MAX_ROUNDS  # one per model round


@pytest.mark.anyio
async def test_dashes_are_removed(fake_model):
    fake_model([{"content": "Close race \u2014 really close."}])
    events = await run("Hi!")
    assert events[1]["text"] == "Close race - really close."


@pytest.mark.anyio
async def test_status_says_what_harry_ai_is_doing(fake_model):
    requests = fake_model(LEG_7_CALL, ANSWER)
    events = await run("Show me leg 7 at Boden")
    assert [(e["type"], e.get("state")) for e in events] == [
        ("status", "thinking"), ("status", "looking"), ("tool", None),
        ("status", "thinking"), ("token", None), ("token", None), ("done", None), ("followups", None)]
    assert events[0]["text"] == "Thinking" and events[3]["text"] == "Thinking"
    assert events[1]["text"] == "Looking at leg 7 at Boden"  # present tense before, past tense after
    assert events[2]["label"] == "Looked up leg 7 at Boden"

    # Only for the page: the model never sees a status, and the page gets back only the tool call
    assert [m["role"] for m in requests[1]["messages"]] == ["system", "user", "assistant", "tool"]
    assert [c["name"] for c in events[-2]["calls"]] == ["leg_details"]


@pytest.mark.anyio
async def test_status_comes_before_each_tool_call_in_a_round(fake_model):
    two_calls = [{"tool_calls": [  # two tool calls in one model reply
        {"index": 0, "id": "a", "function": {"name": "leg_details", "arguments": '{"game_type": "V85", "leg": 7, "track": "Boden"}'}},
        {"index": 1, "id": "b", "function": {"name": "leg_details", "arguments": '{"game_type": "V85", "leg": 8, "track": "Boden"}'}},
    ]}]
    requests = fake_model(two_calls, ANSWER)
    events = await run("Show me legs 7 and 8 at Boden")
    steps = [(e["type"], e.get("text") or e.get("label")) for e in events if e["type"] in ("status", "tool")]
    assert steps == [
        ("status", "Thinking"),
        ("status", "Looking at leg 7 at Boden"), ("tool", "Looked up leg 7 at Boden"),
        ("status", "Looking at leg 8 at Boden"), ("tool", "Looked up leg 8 at Boden"),
        ("status", "Thinking"),  # the next round, with both results
    ]
    assert [m["role"] for m in requests[1]["messages"]] == ["system", "user", "assistant", "tool", "tool"]


@pytest.mark.anyio
async def test_status_follows_the_page_language(fake_model):
    fake_model(call("game_overview", '{"game_type": "V85"}'), ANSWER)
    events = await run("Show me the latest game", "sv")  # an English question on the Swedish page
    texts = [e["text"] for e in events if e["type"] == "status"]
    assert texts == ["Tänker", "Tittar på den senaste V85-omgången på Boden", "Tänker"]  # no track: the latest game


@pytest.mark.anyio
@pytest.mark.parametrize("name, arguments", [
    ("make_tea", '{"cups": 2}'),                # a tool that does not exist
    ("leg_details", '{not json'),               # arguments that are not JSON
    ("leg_details", '{"leg": "seven"}'),        # a leg that is not a number
    ("find_horse", '{"game_type": "V85"}'),     # no horse name
])
async def test_status_falls_back_for_unknown_tools_and_bad_arguments(fake_model, name, arguments):
    fake_model(call(name, arguments), ANSWER)
    events = await run("Show me something")
    looking = [e for e in events if e.get("state") == "looking"]
    assert [e["text"] for e in looking] == ["Looking at the race data"]
    assert [e["type"] for e in events][-2:] == ["done", "followups"]  # the answer still finishes


def test_earlier_tool_calls_are_replayed_as_tool_messages():
    past = [
        {"role": "user", "content": "Biggest upset?"},
        {"role": "assistant", "content": "Wiener Sängerknabe at 43.92.",
         "calls": [{"name": "upsets", "arguments": {"game_type": "V85"}, "facts": ["Leg 4 at Åby: ..."]}]},
    ]
    replayed = agent.replay(past)
    assert [m["role"] for m in replayed] == ["user", "assistant", "tool", "assistant"]
    assert replayed[1]["tool_calls"][0]["function"] == {"name": "upsets", "arguments": '{"game_type": "V85"}'}
    assert replayed[2] == {"role": "tool", "tool_call_id": "past_1_0", "content": "Leg 4 at Åby: ..."}
    assert replayed[3]["content"] == "Wiener Sängerknabe at 43.92."


def test_bad_tool_arguments_become_empty():
    assert agent.arguments({"function": {"arguments": "{not json"}}) == {}
    assert agent.arguments({"function": {"arguments": "[1, 2]"}}) == {}
