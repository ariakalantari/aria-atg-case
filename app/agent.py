"""Harry AI, the chat assistant in the sidebar.

It chats freely, like any assistant. When a question is about real races it calls
tools (see tools.py) and answers from what they return, so race facts come from code.

The loop for one question:
1. Send the conversation and the tool list to the model, and stream its answer.
2. If it asked for tools, run them, show their tables on the page, give the results
   back to the model and go again (at most MAX_ROUNDS times).
3. Otherwise its text is the answer.

Nothing is stored on the server. The page sends the last few messages with every question.
"""
import json

import httpx

from . import ask, followups, tools
from .words import answer_language, say

MAX_ROUNDS = 4
NUDGE = "If this answers the question, reply to the user now."  # added to tool results, small models need it

SYSTEM = """You are Harry AI (Harry for short), the assistant on Aria ATG Case, a page about ATG horse racing \
results in Sweden. You are a small model (Qwen 3.5 2B) running on this computer.

You only help with ATG and horse racing: ATG's games, races, odds, favourites, horses, betting words and this page. \
If someone asks for anything else (code, poems, stories, recipes, general trivia), say kindly in one sentence that \
you only help with ATG and racing, and suggest a question you can answer. Never call a tool for that.

Language: the note next to each question says which language to answer in.

People may write in Swedish. ATG's Swedish words: avdelning = leg, omgång = game, spelform = game type, \
favorit = favourite, skräll = upset, vann = won, placering = finishing position, spelprocent = bet share, \
spela på = bet on, mest spelad = most bet on.

Tools: call a tool when the question is about specific races, games, legs, odds, favourites, winners or horses, \
or when real numbers from the races would make your answer better (for example whether betting on favourites pays off). \
Answer greetings and questions about words and rules directly, without tools. \
Earlier tool results in this conversation are real data: use them for follow-up questions when they have \
the answer, otherwise call a tool. Never make up race data or numbers.

With the tools you can show how often favourites won, compare all game types, list every leg of a game, \
show every horse in a leg, find the biggest upsets, find a horse, and show where bettors disagreed with the odds.

Facts you know:
- V-odds means vinnarodds, the win odds that every horse in a race has: what a 1 kr win bet on that horse \
pays back. 2.25 means 2.25 kr.
- The favourite is the horse with the lowest final V-odds. Favourites 2 and 3 are the next lowest.
- Bet share (for example V85%) is the share of the money in that game's pool placed on a horse.
- In a V-game you try to pick the winning horse in every leg (any horse, not only the favourite). \
The more legs you get right, the more you win. V85 and V86 have 8 legs, GS75 has 7, V64 and V65 have 6, \
V5 has 5, V4 has 4 and V3 has 3. dd (Dagens Dubbel) and ld (Lunchdubbel) have 2.
- On this page you, Harry, answered every leg of the three most recent finished games of a game type: \
you named the favourites and said how the favourite did, and plain code checked every one of your answers.

How to answer: short and friendly, at most five sentences or a short list. Give the final answer only, \
never think out loud or correct yourself. Use **bold** for key names and numbers. Do not use em dashes. \
The page shows each tool result as a table, so do not repeat whole tables."""


async def chat(messages: list[dict], game_type: str, lang: str = "en"):
    """Answer the last message. Yields events: tool (with a table), token (text), done, then followups.

    The done event lists the tool calls of this turn with their facts. The page keeps them with
    the answer and sends them back with later questions, so follow-ups ("and in that leg?")
    are answered from real data instead of the model's memory.
    The followups event (ideas for what to ask next) comes after done, so the page can
    finish the answer straight away instead of waiting for the extra model call.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        games = await tools.load(client, game_type)
        conversation = [
            {"role": "system", "content": SYSTEM},
            *replay(messages[:-1]),
            with_page_note(messages[-1], game_type, games, lang),
        ]
        answer, used, views = "", [], []

        for _ in range(MAX_ROUNDS):
            text, calls = "", {}
            async for kind, value in stream(client, conversation):
                if kind == "text":
                    text += value
                    yield {"type": "token", "text": value}
                else:
                    add_tool_part(calls, value)
            answer += text
            if not calls:
                break

            calls = list(calls.values())
            conversation.append({"role": "assistant", "content": text, "tool_calls": calls})
            for call in calls:
                facts, view, label = await tools.run(client, call["function"]["name"], arguments(call), game_type, lang)
                used.append({"name": call["function"]["name"], "arguments": arguments(call), "facts": facts})
                views.append(view)
                yield {"type": "tool", "name": call["function"]["name"], "label": label, "view": view}
                conversation.append({"role": "tool", "tool_call_id": call["id"], "content": "\n".join([*facts, NUDGE])})
        else:  # still asking for tools after the last round
            answer = say(lang, "I could not finish that one. Try asking about one game or one leg.")
            yield {"type": "token", "text": answer}
        yield {"type": "done", "calls": used}

        if answer.strip():  # ideas for what to ask next, in the same language as the answer
            questions = await followups.suggest(client, messages, answer, list(zip(used, views)), game_type, games,
                                                answer_language(messages[-1]["content"], lang))
            yield {"type": "followups", "questions": questions}


def replay(messages: list[dict]) -> list[dict]:
    """Earlier turns the way the model saw them: its tool calls, their results, then its answer."""
    out = []
    for n, message in enumerate(messages):
        calls = message.get("calls") or []
        if calls:
            ids = [f"past_{n}_{i}" for i in range(len(calls))]
            out.append({"role": "assistant", "content": "", "tool_calls": [
                {"id": id, "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
                for id, c in zip(ids, calls)]})
            out += [{"role": "tool", "tool_call_id": id, "content": "\n".join(c["facts"])} for id, c in zip(ids, calls)]
        out.append({"role": message["role"], "content": message["content"]})
    return out


def with_page_note(message: dict, game_type: str, games: list, lang: str = "en") -> dict:
    """Tell the model what the page shows and which language to answer in, next to the question.
    Keeping it out of the system prompt lets the server reuse the cached system prompt and tool list."""
    latest = ", ".join(f"{game.track} on {tools.day(game)}" for game in games) or "none"
    if answer_language(message["content"], lang) == "sv":
        language = (" Answer in Swedish, with ATG's words: avdelning (plural avdelningar), omgång, spelform, "
                    "vann, placering, skräll, favorit, mest spelad, V-odds. Write decimals with a comma, like 43,92.")
    else:
        language = " Answer in English."
    note = f"(The page shows {game_type}. Its latest games: {latest}.{language})"
    return {"role": "user", "content": f"{note}\n\n{message['content']}"}


async def stream(client: httpx.AsyncClient, conversation: list[dict]):
    """Stream one model reply. Yields ("text", str) and ("tool", partial tool call) pieces."""
    body = {
        "messages": conversation,
        "tools": tools.SCHEMAS,
        "stream": True,
        "temperature": 0,  # small models invent less at 0
        "max_tokens": 500,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    async with client.stream("POST", f"{ask.LLM_URL}/v1/chat/completions", json=body, timeout=120) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            for choice in json.loads(line[6:]).get("choices", []):
                delta = choice.get("delta", {})
                if delta.get("content"):
                    # House style: no em or en dashes in anything we show
                    yield "text", delta["content"].replace("\u2014", "-").replace("\u2013", "-")
                for part in delta.get("tool_calls") or []:
                    yield "tool", part


def add_tool_part(calls: dict, part: dict) -> None:
    """Tool calls arrive in pieces: the name first, then the arguments a few characters at a time."""
    call = calls.setdefault(part.get("index", 0), {
        "id": f"call_{len(calls)}", "type": "function", "function": {"name": "", "arguments": ""}})
    call["id"] = part.get("id") or call["id"]
    function = part.get("function", {})
    call["function"]["name"] += function.get("name") or ""
    call["function"]["arguments"] += function.get("arguments") or ""


def arguments(call: dict) -> dict:
    try:
        args = json.loads(call["function"]["arguments"] or "{}")
    except json.JSONDecodeError:
        return {}
    return args if isinstance(args, dict) else {}
