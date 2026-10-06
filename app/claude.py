"""Claude mode: the same questions, tools and prompts, answered by Claude on Microsoft Foundry
instead of the local model. Everything else (fetching, checking, counting) stays the same.

Needs a Foundry key and endpoint in .env: ANTHROPIC_FOUNDRY_API_KEY plus ANTHROPIC_FOUNDRY_RESOURCE or
ANTHROPIC_FOUNDRY_BASE_URL. Lines named AZURE_ANTHROPIC_API_KEY, _ENDPOINT and _DEPLOYMENT work too.
CLAUDE_MODEL picks the deployment. Without it, the newest Sonnet that answers is used.

The rest of the app speaks the local model's chat format, so this file converts to Claude's
format on the way in and back on the way out.
"""
import json
import os
from collections import Counter
from urllib.parse import urlparse

import anthropic

NEWEST_FIRST = ["claude-sonnet-5-5", "claude-sonnet-5", "claude-sonnet-4-6"]
UNSUPPORTED = ("minItems", "maxItems", "maxLength", "minimum", "maximum")  # structured outputs reject these, code checks them
_client: anthropic.AsyncAnthropicFoundry | None = None
_model: str | None = os.getenv("CLAUDE_MODEL") or None
_failed = ""  # why Claude mode could not start, remembered so it is not tried again on every request
USAGE = Counter()  # tokens used since the app started, for the evaluation's cost


class Unavailable(Exception):
    """Claude mode cannot run: no key in .env, or no Sonnet deployment found."""


def setting(*names: str) -> str:
    return next((os.environ[name].strip() for name in names if os.getenv(name, "").strip()), "")


def key() -> str:
    return setting("ANTHROPIC_FOUNDRY_API_KEY", "AZURE_ANTHROPIC_API_KEY")


def base_url() -> str:
    """https://<resource>.services.ai.azure.com/anthropic/, from the resource name or any endpoint URL on it."""
    if resource := setting("ANTHROPIC_FOUNDRY_RESOURCE"):
        return f"https://{resource}.services.ai.azure.com/anthropic/"
    host = urlparse(setting("ANTHROPIC_FOUNDRY_BASE_URL", "AZURE_ANTHROPIC_ENDPOINT")).netloc
    return f"https://{host}/anthropic/" if host else ""


def configured() -> bool:
    return bool(key() and base_url())


def client() -> anthropic.AsyncAnthropicFoundry:
    global _client
    if not configured():
        raise Unavailable("Claude mode needs a key in .env.")
    if _client is None:
        _client = anthropic.AsyncAnthropicFoundry(api_key=key(), base_url=base_url())
    return _client


async def model() -> str:
    """The deployment to use: CLAUDE_MODEL, or the newest Sonnet deployed on the resource (found once)."""
    global _model, _failed
    if _failed:
        raise Unavailable(_failed)
    if _model is None:
        tried = [*NEWEST_FIRST, setting("AZURE_ANTHROPIC_DEPLOYMENT")]  # a named deployment comes last
        try:
            for name in dict.fromkeys(filter(None, tried)):
                try:
                    await client().messages.create(model=name, max_tokens=1, messages=[{"role": "user", "content": "Hi"}])
                except (anthropic.NotFoundError, anthropic.BadRequestError):
                    continue  # not deployed here, try the next one
                _model = name
                break
            else:
                raise Unavailable("No Claude Sonnet deployment found. Set CLAUDE_MODEL in .env.")
        except (Unavailable, anthropic.APIStatusError) as error:  # a wrong key stays wrong until a restart
            _failed = str(error)
            raise Unavailable(_failed) from error
    return _model


async def status() -> dict:
    """Can Claude mode run here? model is the deployment it would use."""
    if not configured():
        return {"ready": False, "model": None, "reason": "no_key"}
    try:
        return {"ready": True, "model": await model()}
    except (Unavailable, anthropic.APIError):
        return {"ready": False, "model": None, "reason": "failed"}


def count(usage) -> None:
    USAGE["input"] += usage.input_tokens + (usage.cache_read_input_tokens or 0) + (usage.cache_creation_input_tokens or 0)
    USAGE["output"] += usage.output_tokens


async def ask(prompt: str, schema: dict, think: bool = False) -> dict:
    """One question, answered as JSON that fits the schema (like the local model's json_schema).
    think lets Claude work it out first: without it, it got 3 of 10 medians wrong (it guessed the middle)."""
    extra = {"thinking": {"type": "adaptive"}, "max_tokens": 4000} if think else {"max_tokens": 300}
    response = await client().messages.create(
        model=await model(),
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": strict(schema)}},
        **extra,
    )
    count(response.usage)
    return json.loads(next(block.text for block in response.content if block.type == "text"))


def strict(schema):
    """The schema in the form structured outputs accept: closed objects, no size limits."""
    if isinstance(schema, list):
        return [strict(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    out = {key: strict(value) for key, value in schema.items() if key not in UNSUPPORTED}
    if out.get("type") == "object":
        out["additionalProperties"] = False
    return out


async def stream(conversation: list[dict], tool_schemas: list[dict]):
    """Stream one reply, like agent.stream: yields ("text", str) and ("tool", call) pieces.
    Claude sends each tool call whole, so each one arrives as a single piece."""
    system, messages = to_claude(conversation)
    tools = [{"name": t["function"]["name"], "description": t["function"]["description"],
              "input_schema": t["function"]["parameters"]} for t in tool_schemas]
    async with client().messages.stream(model=await model(), max_tokens=1024, system=system,
                                        messages=messages, tools=tools) as reply:
        async for text in reply.text_stream:
            yield "text", text
        final = await reply.get_final_message()
    count(final.usage)
    calls = [block for block in final.content if block.type == "tool_use"]
    for index, call in enumerate(calls):
        yield "tool", {"index": index, "id": call.id,
                       "function": {"name": call.name, "arguments": json.dumps(call.input)}}


def to_claude(conversation: list[dict]) -> tuple[str, list[dict]]:
    """The local chat format to Claude's: the system prompt apart, tool calls as tool_use blocks,
    tool results as tool_result blocks in a user turn, and turns of the same role joined."""
    system, messages = "", []
    for message in conversation:
        role, blocks = message["role"], []
        if role == "system":
            system = message["content"]
            continue
        if role == "tool":
            role = "user"
            blocks.append({"type": "tool_result", "tool_use_id": message["tool_call_id"], "content": message["content"]})
        elif message.get("content"):
            blocks.append({"type": "text", "text": message["content"]})
        for call in message.get("tool_calls") or []:
            blocks.append({"type": "tool_use", "id": call["id"], "name": call["function"]["name"],
                           "input": json.loads(call["function"]["arguments"] or "{}")})
        if not blocks:
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += blocks
        else:
            messages.append({"role": role, "content": blocks})
    return system, messages
