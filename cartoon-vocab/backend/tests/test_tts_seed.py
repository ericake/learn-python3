import asyncio
import base64
import json

import httpx
import pytest

from app.assets import tts_seed
from app.assets.tts_seed import TTS_URL, SeedTTS, TTSError, word_prompt

MP3 = b"ID3fake-mp3-bytes"


def run(handler, **kw):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tts = SeedTTS("test-key", client=client, **kw)
    return asyncio.run(tts.synthesize("prompt"))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def fast(_):
        return None
    monkeypatch.setattr(tts_seed.asyncio, "sleep", fast)


def test_request_shape_and_binary_response():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["key"] = req.headers["X-Api-Key"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, content=MP3, headers={"content-type": "audio/mpeg"})

    assert run(handler) == MP3
    assert seen["url"] == TTS_URL and seen["key"] == "test-key"
    assert seen["body"]["model"] == "seed-audio-1.0"
    assert seen["body"]["audio_config"] == {"format": "mp3", "sample_rate": 48000, "pitch_rate": 0,
                                            "speech_rate": 0, "loudness_rate": 0}
    assert seen["body"]["watermark"] == {}


def test_json_base64_response():
    b64 = base64.b64encode(MP3).decode()
    assert run(lambda r: httpx.Response(200, json={"data": {"audio": b64}})) == MP3
    assert run(lambda r: httpx.Response(200, json={"data": b64})) == MP3


def test_json_url_response():
    def handler(req):
        if req.url.path.endswith("a.mp3"):
            return httpx.Response(200, content=MP3)
        return httpx.Response(200, json={"data": {"url": "https://cdn.example.com/a.mp3"}})

    assert run(handler) == MP3


def test_retries_5xx_then_succeeds():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, content=MP3, headers={"content-type": "audio/mpeg"})

    assert run(handler) == MP3 and calls["n"] == 3


def test_4xx_is_not_retried():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(401, text="bad key")

    with pytest.raises(TTSError):
        run(handler)
    assert calls["n"] == 1


def test_prompt_is_english_clean_voice():
    p = word_prompt("A warm, cheerful young {accent} female voice", "en-GB", "puddle", slow=True)
    assert "British" in p and '"puddle."' in p and "no background music" in p and "slowly" in p
