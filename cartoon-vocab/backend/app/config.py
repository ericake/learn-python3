"""运行配置：全部来自环境变量，密钥只在服务端读取。"""

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """读取 backend/.env（不覆盖已存在的环境变量）。"""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


if not os.environ.get("PYTEST_CURRENT_TEST"):
    _load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'data' / 'app.db'}"))
    media_dir: Path = field(default_factory=lambda: Path(_env("MEDIA_DIR", str(BACKEND_DIR / "data" / "media"))))
    media_base_url: str = field(default_factory=lambda: _env("MEDIA_BASE_URL", "/media"))

    # 词表提取（Claude）。未配置密钥时使用离线规则提取。
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "claude-opus-5-5"))

    # 语音（字节 seed-audio）。未配置密钥时由浏览器朗读兜底（仅开发用）。
    volc_tts_api_key: str = field(default_factory=lambda: _env("VOLC_TTS_API_KEY"))
    tts_model: str = field(default_factory=lambda: _env("TTS_MODEL", "seed-audio-1.0"))
    tts_concurrency: int = field(default_factory=lambda: int(_env("TTS_CONCURRENCY", "8")))
    tts_slow_speech_rate: int = field(default_factory=lambda: int(_env("TTS_SLOW_SPEECH_RATE", "-25")))
    voice_profile: str = field(
        default_factory=lambda: _env("VOICE_PROFILE", "A warm, cheerful young {accent} female voice")
    )

    # 生图：placeholder（内置 emoji 卡片）为默认，正式服务商待定。
    image_provider: str = field(default_factory=lambda: _env("IMAGE_PROVIDER", "placeholder"))

    @property
    def use_llm(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def use_seed_tts(self) -> bool:
        return bool(self.volc_tts_api_key)


settings = Settings()
