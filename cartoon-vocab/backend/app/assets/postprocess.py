"""音频后处理（技术文档 6.3.3）：去首尾静音、统一响度、转单声道 mp3。"""

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

DURATION_LIMITS_MS = {"word": (300, 2500), "phrase": (600, 4000), "sentence": (300, 12000), "system": (300, 6000)}

_FILTER = (
    "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
    "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
    "loudnorm=I=-16:TP=-1.5:LRA=11"
)


class AudioQCError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


async def _run(*args: str) -> bytes:
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise AudioQCError(err.decode(errors="ignore")[-300:])
    return out


async def process_audio(data: bytes, kind: str) -> tuple[bytes, int]:
    """返回 (处理后的 mp3, 时长毫秒)。时长超出范围抛出 AudioQCError 以触发重新生成。"""
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d) / "in.mp3", Path(d) / "out.mp3"
        src.write_bytes(data)
        await _run("ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-af", _FILTER,
                   "-ac", "1", "-ar", "44100", "-b:a", "64k", str(dst))
        probe = await _run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(dst))
        duration_ms = int(float(json.loads(probe)["format"]["duration"]) * 1000)
        lo, hi = DURATION_LIMITS_MS[kind]
        if not lo <= duration_ms <= hi:
            raise AudioQCError(f"duration {duration_ms}ms outside {lo}-{hi}ms for {kind}")
        return dst.read_bytes(), duration_ms
