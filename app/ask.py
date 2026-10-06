"""Step 3: ask the local LLM (a llama.cpp server) two small questions per leg.

Small models get confused easily, so each question is kept tiny:
- Step A shows only the odds, sorted, with no results, and asks for the 3 favourites.
  (Shown odds and results together, the model mixes up "favourite" and "winner".)
- Step B shows only the official result and asks where the chosen favourite finished.
Every answer is forced into a JSON schema that only allows names and positions from
that leg, so the model cannot invent a horse.
"""
import json
import os

import httpx

from .clean import Leg, Runner

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
        f"List the {WORDS[count]} favourites by name, lowest odds first."
    )
    names = {"type": "string", "enum": [r.name for r in leg.runners]}
    schema = {
        "type": "object",
        "properties": {
            "favourites": {"type": "array", "items": names, "minItems": count, "maxItems": count},
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


async def ask(client: httpx.AsyncClient, prompt: str, schema: dict) -> dict:
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


async def ask_leg(client: httpx.AsyncClient, leg: Leg) -> dict:
    """Both steps for one leg. Step B uses the favourite the model picked in step A."""
    prompt, schema = odds_question(leg)
    favourites = (await ask(client, prompt, schema))["favourites"]
    prompt, schema = result_question(leg, favourites[0])
    result = await ask(client, prompt, schema)
    return {"favourites": favourites, "position": result["position"], "won": result["won"]}


async def status(client: httpx.AsyncClient) -> str:
    """'ready', 'loading' (model still loading) or 'offline' (server not up yet)."""
    try:
        response = await client.get(f"{LLM_URL}/health", timeout=2)
    except httpx.HTTPError:
        return "offline"
    return "ready" if response.status_code == 200 else "loading"
