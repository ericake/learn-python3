"""字节跳动 seed-audio TTS 客户端（技术文档 6.3）。

注意：接口响应格式尚未联调确认，这里兼容几种常见形式，确认后删除多余分支。
密钥只从环境变量 VOLC_TTS_API_KEY 读取，日志中不打印请求头。
"""

import asyncio
import base64
import logging

import httpx

log = logging.getLogger(__name__)

TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/create"


class TTSError(RuntimeError):
    pass


class SeedTTS:
    provider = "bytedance_seed_audio"

    def __init__(self, api_key: str, model: str = "seed-audio-1.0", concurrency: int = 8,
                 client: httpx.AsyncClient | None = None):
        self._key = api_key
        self._model = model
        self._sem = asyncio.Semaphore(concurrency)
        self._http = client or httpx.AsyncClient(timeout=300)

    def body(self, text_prompt: str, speech_rate: int = 0) -> dict:
        return {
            "model": self._model,
            "text_prompt": text_prompt,
            "audio_config": {
                "format": "mp3",
                "sample_rate": 48000,
                "pitch_rate": 0,
                "speech_rate": speech_rate,
                "loudness_rate": 0,
            },
            "watermark": {},
        }

    async def synthesize(self, text_prompt: str, speech_rate: int = 0) -> bytes:
        async with self._sem:
            delay = 1.0
            for attempt in range(4):
                try:
                    r = await self._http.post(
                        TTS_URL, json=self.body(text_prompt, speech_rate), timeout=300,
                        headers={"X-Api-Key": self._key, "Content-Type": "application/json"},
                    )
                except httpx.TransportError as e:
                    err: Exception = e
                else:
                    if r.status_code == 429 or r.status_code >= 500:
                        err = TTSError(f"HTTP {r.status_code}")
                    elif r.status_code >= 400:
                        raise TTSError(f"HTTP {r.status_code}: {r.text[:300]}")
                    else:
                        return await self._audio_from_response(r)
                if attempt == 3:
                    raise TTSError(f"TTS failed after retries: {err}")
                log.warning("TTS retry %s after %s", attempt + 1, err)
                await asyncio.sleep(delay)
                delay *= 2
        raise AssertionError("unreachable")

    async def _audio_from_response(self, r: httpx.Response) -> bytes:
        ctype = r.headers.get("content-type", "")
        if ctype.startswith("audio/") or ctype == "application/octet-stream":
            return r.content
        try:
            data = r.json()
        except ValueError as e:
            raise TTSError(f"unexpected TTS response type {ctype!r}") from e
        # TODO: 联调后只保留实际使用的分支
        payload = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(payload, str):
            return base64.b64decode(payload)
        if isinstance(payload, dict):
            for k in ("audio", "data", "audio_data"):
                if isinstance(payload.get(k), str):
                    return base64.b64decode(payload[k])
            for k in ("url", "audio_url"):
                if isinstance(payload.get(k), str):
                    return (await self._http.get(payload[k], timeout=60)).content
        raise TTSError(f"unrecognised TTS response keys: {list(data)[:10] if isinstance(data, dict) else type(data)}")


ACCENT_DESC = {"en-GB": "British", "en-US": "American"}


def word_prompt(voice_profile: str, accent: str, text: str, slow: bool = False) -> str:
    voice = voice_profile.format(accent=ACCENT_DESC.get(accent, "British"))
    manner = ("speaking slowly and very clearly, stretching each syllable gently" if slow
              else "speaking clearly")
    return (f"{voice}, {manner} to a six-year-old child. Studio quality, no background music, "
            f"no sound effects, no other speakers. She says: \"{text}.\"")


def sentence_prompt(voice_profile: str, accent: str, sentence: str, keyword: str) -> str:
    voice = voice_profile.format(accent=ACCENT_DESC.get(accent, "British"))
    return (f"{voice}, reading naturally to a six-year-old child and slightly emphasizing the word "
            f"\"{keyword}\". Studio quality, no background music, no sound effects, no other speakers. "
            f"She says: \"{sentence}\"")
