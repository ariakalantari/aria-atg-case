"""The web app: one page plus a small streaming API."""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path as FilePath
from typing import Annotated, Literal

import anthropic
import httpx
from fastapi import FastAPI, Path
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, ask, claude, download
from .report import report

log = logging.getLogger("uvicorn.error")  # uvicorn's own logger, so these lines show in the terminal


@asynccontextmanager
async def lifespan(_app):
    task = asyncio.create_task(download.announce())
    yield
    task.cancel()


app = FastAPI(title="Aria ATG Case", lifespan=lifespan)
GAME_TYPE_PATTERN = r"^[A-Za-z0-9]{1,8}$"
Mode = Literal["local", "claude"]  # which model answers: the local one, or Claude on Foundry


class PastCall(BaseModel):
    """A tool call from an earlier answer, sent back so follow-up questions have the data."""
    name: str = Field(max_length=40)
    arguments: dict = {}
    facts: list[Annotated[str, Field(max_length=600)]] = Field(default=[], max_length=40)


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)
    calls: list[PastCall] = Field(default=[], max_length=6)


class Chat(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=12)  # the page sends only the last few
    game_type: str = Field(pattern=GAME_TYPE_PATTERN)
    lang: Literal["en", "sv"] = "en"
    mode: Mode = "local"


@app.get("/api/report/{game_type}")
async def get_report(game_type: str = Path(pattern=GAME_TYPE_PATTERN), mode: Mode = "local"):
    """The report for one game type, streamed so the page fills in leg by leg."""
    return stream_lines(report(game_type, mode=mode), f"Report for {game_type}")


@app.post("/api/chat")
async def post_chat(chat: Chat):
    """One answer from the assistant, streamed word by word."""
    messages = [message.model_dump() for message in chat.messages]
    return stream_lines(agent.chat(messages, chat.game_type, chat.lang, chat.mode), "Chat")


@app.get("/api/status")
async def get_status():
    """Which models are ready. While the local one is still downloading, also how far it has come."""
    async with httpx.AsyncClient() as client:
        return await download.status(client)


def stream_lines(events, what: str) -> StreamingResponse:
    """Send events as JSON lines (one per line). Errors become an error event with a short code,
    so the page can show it in its own language."""

    async def lines():
        try:
            async for event in events:
                yield json.dumps(event) + "\n"
        except httpx.HTTPError as error:
            yield json.dumps(error_event(error)) + "\n"
        except (claude.Unavailable, anthropic.APIError) as error:
            log.warning("%s: Claude failed: %s", what, error)
            yield json.dumps({"type": "error", "code": "claude_unavailable",
                              "message": "Claude is not available right now. Switch to Local mode, or check the key in .env."}) + "\n"
        except Exception:
            log.exception("%s failed", what)
            yield json.dumps({"type": "error", "code": "failed", "message": "Something went wrong. Please try again."}) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson")


def error_event(error: httpx.HTTPError) -> dict:
    try:
        url = str(error.request.url)
    except RuntimeError:
        url = ""
    if url.startswith(ask.LLM_URL):
        return {"type": "error", "code": "model_not_ready",
                "message": "The local model is not ready yet. It may still be downloading or loading."}
    return {"type": "error", "code": "atg_unavailable",
            "message": "Could not get data from ATG right now. Please try again in a moment."}


app.mount("/", StaticFiles(directory=FilePath(__file__).parent.parent / "static", html=True), name="static")
