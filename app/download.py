"""The first start: which models are ready, and how far the download of Harry's model has come,
for the page (/api/status) and the terminal.

llama.cpp saves the model in the shared "models" volume, in Hugging Face's cache layout:
models--<owner>--<name>/blobs/<sha256>, called <sha256>.downloadInProgress until it is complete.
Hugging Face's manifest (the same one llama.cpp reads) gives the file's sha256 and full size.
"""
import asyncio
import logging
import os
from pathlib import Path

import httpx

from . import ask, claude
from .ask import MODEL

MODELS = Path(os.getenv("MODELS_DIR", "/models"))
log = logging.getLogger("uvicorn.error")  # uvicorn's own logger, so these lines show in the terminal
_file: dict | None = None  # the model file's sha256 and size, looked up once


async def model_file(client: httpx.AsyncClient) -> dict | None:
    """The model file's sha256 and size from Hugging Face, or None if it cannot be reached."""
    global _file
    if _file is None:
        repo, _, tag = MODEL.partition(":")
        try:
            response = await client.get(f"https://huggingface.co/v2/{repo}/manifests/{tag or 'latest'}",
                                        headers={"User-Agent": "llama-cpp"}, timeout=5)
            gguf = response.json()["ggufFile"]
            _file = {"sha": gguf["blobId"].removeprefix("sha256:"), "size": gguf["size"]}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None
    return _file


async def progress(client: httpx.AsyncClient) -> dict | None:
    """{"done": bytes saved so far, "total": bytes}, or None when the size is unknown."""
    file = await model_file(client)
    if not file:
        return None
    blobs = MODELS / ("models--" + MODEL.partition(":")[0].replace("/", "--")) / "blobs"
    for name in (file["sha"], file["sha"] + ".downloadInProgress"):
        if (blobs / name).exists():
            return {"done": (blobs / name).stat().st_size, "total": file["size"]}
    return {"done": 0, "total": file["size"]}


async def status(client: httpx.AsyncClient) -> dict:
    """Is the local model ready (and while it downloads, how far it has come)? Can Claude mode run?"""
    state, on = await ask.status(client), await claude.status()
    # model is the Hugging Face id, for the setup screen's source line; name is for people
    result = {"llm": state, "name": ask.display(MODEL), "model": MODEL,
              "claude": {"ready": on["ready"], "name": on["model"] and ask.display(on["model"])}}
    if state == "offline":  # llama.cpp only starts listening once the model is downloaded
        result["download"] = await progress(client)
    return result


async def announce():
    """Say in the terminal where to open the page, and how the first-start download is going.
    llama.cpp prints nothing while it downloads, so without this the terminal looks stuck."""
    log.info("Aria ATG Case is running. Open http://localhost:8000")
    said = ""
    async with httpx.AsyncClient() as client:
        on = (await status(client))["claude"]
        log.info(f"Claude mode is on: {on['name']}." if on["ready"] else "Claude mode is off (it needs a Foundry key in .env).")
        while (now := await status(client))["llm"] != "ready":
            line = "Starting Harry's model..."
            if (got := now.get("download")) and got["done"] < got["total"]:
                line = (f"Downloading Harry's model, only on the first start: {got['done'] * 100 // got['total'] // 10 * 10}%"
                        f" of {got['total'] / 1e9:.1f} GB. The page shows the progress too.")
            elif got or now["llm"] == "loading":
                line = "Loading Harry's model into memory..."
            if line != said:
                log.info(line)
                said = line
            await asyncio.sleep(2)
    log.info("Harry is ready.")
