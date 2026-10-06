"""Step 3: the LLM answers the four questions: the local model (a llama.cpp server), or Claude in Claude mode.

Small models get confused easily, so each question is kept tiny:
- Step A shows only the odds, sorted, with no results, and asks for the 3 favourites with their odds.
  (Shown odds and results together, the model mixes up "favourite" and "winner".)
- Step B shows only the official result and asks where the chosen favourite finished.
- In Claude mode, once per report, the summary question shows the model its own per-leg answers
  and asks how many legs the favourite won and the median finishing position. (The local 2B model
  cannot count a 24-line list, so in Local mode code counts its answers, see report.py.)
Every answer is forced into a JSON schema that only allows names, odds and positions from
that leg, so the model cannot invent a horse.
"""
import json
import os
import re

import httpx

from . import claude
from .clean import Leg, Runner
from .words import ordinal

LLM_URL = os.getenv("LLM_URL", "http://localhost:8080")
MODEL = os.getenv("LLM_MODEL", "unsloth/Qwen3.5-2B-GGUF:Q4_K_M")
WORDS = ["zero", "one", "two", "three"]


def odds_question(leg: Leg) -> tuple[str, dict]:
    count = min(3, len(leg.runners))
    board = "\n".join(f"- {r.name}: {r.odds:.2f}" for r in leg.runners)
    prompt = (
        "Win odds (v_odds) for each horse in one race. "
        "The favourite is the horse with the LOWEST odds.\n\n"
        f"{board}\n\n"
        f"List the {WORDS[count]} favourites with their odds, lowest odds first."
    )
    favourite = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "enum": [r.name for r in leg.runners]},
            "odds": {"type": "string", "enum": list(dict.fromkeys(f"{r.odds:.2f}" for r in leg.runners))},
        },
        "required": ["name", "odds"],
    }
    schema = {
        "type": "object",
        "properties": {
            "favourites": {"type": "array", "items": favourite, "minItems": count, "maxItems": count},
        },
        "required": ["favourites"],
    }
    return prompt, schema


def result_question(leg: Leg, horse: str) -> tuple[str, dict]:
    ordered = sorted(leg.runners, key=result_order)
    lines = "\n".join(result_line(r) for r in ordered)
    prompt = f"Race result:\n{lines}\n\nIn which position did {horse} finish? Did {horse} win?"
    schema = {
        "type": "object",
        "properties": {
            "position": {"type": "string", "enum": list(dict.fromkeys(r.finish for r in ordered))},
            "won": {"type": "boolean"},
        },
        "required": ["position", "won"],
    }
    return prompt, schema


def summary_question(rows: list[tuple[str, str, int]]) -> tuple[str, dict]:
    """rows: (leg, finish label, place as a number) from the model's own answers, one per leg."""
    lines = "\n".join(f"- {leg}: {summary_line(finish, place)}" for leg, finish, place in rows)
    prompt = (
        f"Where the favourite finished in each of {len(rows)} legs:\n{lines}\n\n"
        "In how many legs did the favourite win? What is the median finishing position?"
    )
    schema = {
        "type": "object",
        "properties": {
            "wins": {"type": "integer", "minimum": 0, "maximum": len(rows)},
            "median": {"type": "number"},
        },
        "required": ["wins", "median"],
    }
    return prompt, schema


def summary_line(finish: str, place: int) -> str:
    """'1st, won', or what a disqualified or unplaced favourite counts as (the rules in check.py)."""
    if finish == "disqualified":
        return f"disqualified, counts as last ({ordinal(place)})"
    if finish == "unplaced":
        return f"outside the top {place - 1}, counts as {ordinal(place)}"
    return f"{ordinal(place)}, won" if place == 1 else ordinal(place)


def result_line(runner: Runner) -> str:
    # "Position 3: Name" works much better for small models than "3. Name"
    if runner.finish == "disqualified":
        return f"Disqualified: {runner.name}"
    if runner.finish == "unplaced":
        return f"Unplaced: {runner.name}"
    return f"Position {runner.finish}: {runner.name}"


def result_order(runner: Runner) -> int:
    if runner.finish.isdigit():
        return int(runner.finish)
    return 900 if runner.finish == "unplaced" else 999


async def ask(client: httpx.AsyncClient, prompt: str, schema: dict, mode: str = "local", think: bool = False) -> dict:
    if mode == "claude":
        return await claude.ask(prompt, schema, think)
    body = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 200,  # answers are short, this stops runaway output
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}},
    }
    response = await client.post(f"{LLM_URL}/v1/chat/completions", json=body, timeout=120)
    response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])


async def ask_leg(client: httpx.AsyncClient, leg: Leg, mode: str = "local") -> dict:
    """Both steps for one leg. Step B uses the favourite the model picked in step A."""
    prompt, schema = odds_question(leg)
    picks = (await ask(client, prompt, schema, mode))["favourites"][:3]
    favourites = [pick["name"] for pick in picks]
    prompt, schema = result_question(leg, favourites[0])
    result = await ask(client, prompt, schema, mode)
    return {"favourites": favourites, "odds": [float(pick["odds"]) for pick in picks],
            "position": result["position"], "won": result["won"]}


async def ask_summary(client: httpx.AsyncClient, rows: list[tuple[str, str, int]], mode: str = "local") -> dict:
    """The last two questions (how often the favourite won, its median finish), from the model's own answers."""
    answer = await ask(client, *summary_question(rows), mode, think=True)  # counting 24 lines needs thought
    return {"wins": int(answer["wins"]), "median": float(answer["median"])}


def display(model: str) -> str:
    """A model's name for people: 'unsloth/Qwen3.5-2B-GGUF:Q4_K_M' -> 'Qwen 3.5 2B', and a Claude
    deployment such as 'claude-sonnet-4-6' or 'my-sonnet-4-6' -> 'Claude Sonnet 4.6'."""
    if found := re.search(r"(sonnet|opus|haiku|fable)-(\d+)(?:-(\d+))?", model, re.IGNORECASE):
        family, major, minor = found.groups()
        return f"Claude {family.capitalize()} {major}{'.' + minor if minor else ''}"
    if found := re.search(r"Qwen([\d.]+)-(\d+B)", model, re.IGNORECASE):
        return f"Qwen {found[1]} {found[2]}"
    return model


async def model_name(mode: str) -> str:
    """The model that answers in this mode: the local one, or the Claude deployment."""
    return await claude.model() if mode == "claude" else MODEL


async def status(client: httpx.AsyncClient) -> str:
    """'ready', 'loading' (model still loading) or 'offline' (server not up yet)."""
    try:
        response = await client.get(f"{LLM_URL}/health", timeout=2)
    except httpx.HTTPError:
        return "offline"
    return "ready" if response.status_code == 200 else "loading"
