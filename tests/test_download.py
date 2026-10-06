import httpx
import pytest

from app import download

SHA = "aaf42c8b"
MANIFEST = {"ggufFile": {"rfilename": "Qwen3.5-2B-Q4_K_M.gguf", "blobId": f"sha256:{SHA}", "size": 1000}}


@pytest.fixture
def blobs(tmp_path, monkeypatch):
    """An empty models folder, and a fresh lookup of the model file."""
    monkeypatch.setattr(download, "MODELS", tmp_path)
    monkeypatch.setattr(download, "_file", None)
    folder = tmp_path / "models--unsloth--Qwen3.5-2B-GGUF" / "blobs"
    folder.mkdir(parents=True)
    return folder


def client(answer=MANIFEST, status=200):
    asked = []

    def handle(request):
        asked.append(request)
        return httpx.Response(status, json=answer)

    return httpx.AsyncClient(transport=httpx.MockTransport(handle)), asked


@pytest.mark.anyio
async def test_nothing_downloaded_yet(blobs):
    http, asked = client()
    assert await download.progress(http) == {"done": 0, "total": 1000}
    assert str(asked[0].url) == "https://huggingface.co/v2/unsloth/Qwen3.5-2B-GGUF/manifests/Q4_K_M"


@pytest.mark.anyio
async def test_half_downloaded(blobs):
    (blobs / f"{SHA}.downloadInProgress").write_bytes(b"x" * 400)
    http, _ = client()
    assert await download.progress(http) == {"done": 400, "total": 1000}


@pytest.mark.anyio
async def test_downloaded(blobs):
    (blobs / SHA).write_bytes(b"x" * 1000)
    http, _ = client()
    assert await download.progress(http) == {"done": 1000, "total": 1000}


@pytest.mark.anyio
async def test_size_is_looked_up_once(blobs):
    http, asked = client()
    await download.progress(http)
    await download.progress(http)
    assert len(asked) == 1


@pytest.mark.anyio
async def test_unknown_size_when_hugging_face_fails(blobs):
    http, _ = client({"error": "not found"}, 404)
    assert await download.progress(http) is None


@pytest.mark.anyio
async def test_status_has_what_the_setup_screen_reads(blobs, monkeypatch):
    """The page reads all of these while it waits for the model.
    Without model it stopped checking and the setup screen froze."""
    async def offline(client):
        return "offline"

    async def no_claude():
        return {"ready": False, "model": None}

    monkeypatch.setattr(download.ask, "status", offline)
    monkeypatch.setattr(download.claude, "status", no_claude)
    http, _ = client()
    assert await download.status(http) == {
        "llm": "offline", "name": "Qwen 3.5 2B", "model": "unsloth/Qwen3.5-2B-GGUF:Q4_K_M",
        "claude": {"ready": False, "name": None}, "download": {"done": 0, "total": 1000}}
