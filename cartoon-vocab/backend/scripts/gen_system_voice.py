"""预生成英文系统提示语音（技术文档 6.3.4），输出到 MEDIA_DIR/voice/<key>.mp3。

用法：VOLC_TTS_API_KEY=... python -m scripts.gen_system_voice [--accent en-GB] [--force]
生成后请人工试听；不满意的删掉对应文件重新运行即可。
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.assets.postprocess import AudioQCError, ffmpeg_available, process_audio  # noqa: E402
from app.assets.tts_seed import ACCENT_DESC, SeedTTS  # noqa: E402
from app.config import settings  # noqa: E402
from app.lessons.voices import SYSTEM_VOICES  # noqa: E402


async def main(accent: str, force: bool) -> int:
    if not settings.use_seed_tts:
        print("请先设置环境变量 VOLC_TTS_API_KEY")
        return 1
    tts = SeedTTS(settings.volc_tts_api_key, settings.tts_model, settings.tts_concurrency)
    out_dir = settings.media_dir / "voice"
    out_dir.mkdir(parents=True, exist_ok=True)
    voice = settings.voice_profile.format(accent=ACCENT_DESC.get(accent, "British"))

    async def one(key: str, text: str) -> None:
        path = out_dir / f"{key}.mp3"
        if path.exists() and not force:
            print(f"skip {key}")
            return
        prompt = (f"{voice}, speaking warmly and clearly to a six-year-old child, cheerful and encouraging. "
                  f"Studio quality, no background music, no sound effects, no other speakers. She says: \"{text}\"")
        for _ in range(3):
            raw = await tts.synthesize(prompt)
            try:
                data = (await process_audio(raw, "system"))[0] if ffmpeg_available() else raw
                break
            except AudioQCError as e:
                print(f"retry {key}: {e}")
        else:
            print(f"FAILED {key}")
            return
        path.write_bytes(data)
        print(f"ok   {key}: {text}")

    await asyncio.gather(*(one(k, t) for k, t in SYSTEM_VOICES.items()))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--accent", default="en-GB", choices=sorted(ACCENT_DESC))
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.accent, a.force)))
