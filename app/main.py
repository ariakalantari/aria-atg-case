"""The web app: one page plus a small streaming API."""
import json
import logging
from pathlib import Path as FilePath
from typing import Annotated, Literal

import httpx
from fastapi import FastAPI, Path
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, ask
from .report import report

log = logging.getLogger(__name__)
app = FastAPI(title="Aria ATG Case")
GAME_TYPE = r"^[A-Za-z0-9]{1,8}$"


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
    game_type: str = Field(pattern=GAME_TYPE)
    lang: Literal["en", "sv"] = "en"


@app.get("/api/report/{game_type}")
async def get_report(game_type: str = Path(pattern=GAME_TYPE)):
    """The report for one game type, streamed so the page fills in leg by leg."""
    return stream_lines(report(game_type), f"Report for {game_type}")


@app.post("/api/chat")
async def post_chat(chat: Chat):
    """One answer from the assistant, streamed word by word."""
    messages = [message.model_dump() for message in chat.messages]
    return stream_lines(agent.chat(messages, chat.game_type, chat.lang), "Chat")


@app.get("/api/status")
async def get_status():
    async with httpx.AsyncClient() as client:
        return {"llm": await ask.status(client), "model": ask.MODEL}


def stream_lines(events, what: str) -> StreamingResponse:
    """Send events as JSON lines (one per line). Errors become an error event with a short code,
    so the page can show it in its own language."""

    async def lines():
        try:
            async for event in events:
                yield json.dumps(event) + "\n"
        except httpx.HTTPError as error:
            yield json.dumps(error_event(error)) + "\n"
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
