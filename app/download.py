"""The first start downloads Harry's model. This measures how far it has come, for the page and the terminal.

llama.cpp saves the model in the shared "models" volume, in Hugging Face's cache layout:
models--<owner>--<name>/blobs/<sha256>, called <sha256>.downloadInProgress until it is complete.
Hugging Face's manifest (the same one llama.cpp reads) gives the file's sha256 and full size.
"""
import os
from pathlib import Path

import httpx

from .ask import MODEL

MODELS = Path(os.getenv("MODELS_DIR", "/models"))
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
