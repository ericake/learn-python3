"""素材生成：图片、单词音频（正常/慢速）、原句音频；带全局复用与内容哈希去重。"""

import hashlib
import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, settings
from ..models import Asset, CostLedger, EpisodeItem, VocabItem
from . import tts_seed
from .images import ImageProvider, full_prompt, get_image_provider
from .postprocess import AudioQCError, ffmpeg_available, process_audio
from .storage import LocalStorage, storage

log = logging.getLogger(__name__)

MAX_IMAGE_REGEN = 3


def _hash(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class AssetGenerator:
    def __init__(self, db: Session, cfg: Settings = settings, store: LocalStorage = storage,
                 tts: tts_seed.SeedTTS | None = None, images: ImageProvider | None = None,
                 episode_id: str | None = None):
        self.db = db
        self.cfg = cfg
        self.store = store
        self.episode_id = episode_id
        if tts is None and cfg.use_seed_tts:
            tts = tts_seed.SeedTTS(cfg.volc_tts_api_key, cfg.tts_model, cfg.tts_concurrency)
        self.tts = tts
        self.images = images or get_image_provider(cfg.image_provider)

    # ---------- 通用 ----------
    def _cached(self, content_hash: str) -> Asset | None:
        return self.db.scalars(
            select(Asset).where(Asset.content_hash == content_hash, Asset.status == "ready").limit(1)
        ).first()

    def _ledger(self, provider: str, operation: str, units: float, unit: str) -> None:
        self.db.add(CostLedger(episode_id=self.episode_id, provider=provider, operation=operation, units=units, unit=unit))

    # ---------- 音频 ----------
    async def audio(self, *, text_prompt: str, speak_text: str, kind: str, speech_rate: int = 0,
                    browser_rate: float = 1.0) -> Asset:
        """生成一段音频。未配置 TTS 时返回浏览器朗读兜底素材（storage_key 为空）。"""
        if self.tts is None:
            h = _hash("browser", speak_text, browser_rate)
            if (a := self._cached(h)) is not None:
                return a
            a = Asset(kind="audio", provider="browser", prompt=text_prompt, speak_text=speak_text,
                      params={"rate": browser_rate}, content_hash=h)
            self.db.add(a)
            self.db.flush()
            return a

        body = self.tts.body(text_prompt, speech_rate)
        h = _hash(self.tts.provider, body)
        if (a := self._cached(h)) is not None:
            return a
        last_err: Exception | None = None
        for _ in range(3):  # 首次 + 最多重试 2 次
            raw = await self.tts.synthesize(text_prompt, speech_rate)
            self._ledger(self.tts.provider, f"tts_{kind}", len(text_prompt), "chars")
            try:
                data, dur = await process_audio(raw, kind) if ffmpeg_available() else (raw, None)
                break
            except AudioQCError as e:
                last_err = e
                log.warning("audio QC failed (%s), regenerating", e)
        else:
            raise AudioQCError(str(last_err))
        key = f"audio/{h[:2]}/{h}.mp3"
        self.store.put(key, data)
        a = Asset(kind="audio", provider=self.tts.provider, prompt=text_prompt, speak_text=speak_text,
                  storage_key=key, mime="audio/mpeg", bytes=len(data), duration_ms=dur,
                  params=body["audio_config"], content_hash=h)
        self.db.add(a)
        self.db.flush()
        return a

    async def word_audio(self, vocab: VocabItem) -> None:
        kind = "phrase" if vocab.type == "phrase" else "word"
        if vocab.audio_normal_id is None:
            a = await self.audio(
                text_prompt=tts_seed.word_prompt(self.cfg.voice_profile, vocab.accent, vocab.text),
                speak_text=vocab.text, kind=kind)
            vocab.audio_normal_id = a.id
        if vocab.audio_slow_id is None:
            a = await self.audio(
                text_prompt=tts_seed.word_prompt(self.cfg.voice_profile, vocab.accent, vocab.text, slow=True),
                speak_text=vocab.text, kind=kind, speech_rate=self.cfg.tts_slow_speech_rate, browser_rate=0.7)
            vocab.audio_slow_id = a.id

    async def sentence_audio(self, item: EpisodeItem) -> None:
        if not item.source_sentence:
            return
        a = await self.audio(
            text_prompt=tts_seed.sentence_prompt(self.cfg.voice_profile, item.vocab.accent,
                                                 item.source_sentence, item.vocab.text),
            speak_text=item.source_sentence, kind="sentence")
        item.sentence_audio_id = a.id

    # ---------- 图片 ----------
    async def image(self, item: EpisodeItem, variant: int = 0) -> Asset:
        prompt = full_prompt(item.image_prompt or item.vocab.text)
        h = _hash(self.images.name, prompt, item.vocab.emoji, variant)
        if (a := self._cached(h)) is None:
            data = await self.images.generate(prompt, emoji=item.vocab.emoji, variant=variant)
            key = f"image/{h[:2]}/{h}.{self.images.ext}"
            self.store.put(key, data)
            if self.images.name != "placeholder":
                self._ledger(self.images.name, "image", 1, "images")
            a = Asset(kind="image", provider=self.images.name, prompt=prompt, storage_key=key,
                      mime=self.images.mime, bytes=len(data), params={"variant": variant}, content_hash=h)
            self.db.add(a)
            self.db.flush()
        return a

    async def item_image(self, item: EpisodeItem) -> None:
        if item.image_id is not None:
            return
        vocab = item.vocab
        if vocab.default_image_id is not None:
            item.image_id = vocab.default_image_id
            return
        a = await self.image(item)
        item.image_id = a.id
        vocab.default_image_id = a.id

    async def regenerate_image(self, item: EpisodeItem) -> Asset:
        if item.image_regen_count >= MAX_IMAGE_REGEN:
            raise ValueError("每个条目最多换图 3 次")
        if item.image_id:
            old = self.db.get(Asset, item.image_id)
            if old is not None:
                old.status = "rejected"  # 被家长换掉的图不再复用
                if item.vocab.default_image_id == old.id:
                    item.vocab.default_image_id = None
        item.image_regen_count += 1
        a = await self.image(item, variant=item.image_regen_count)
        item.image_id = a.id
        item.vocab.default_image_id = a.id
        return a

    async def all_for_item(self, item: EpisodeItem) -> None:
        await self.item_image(item)
        await self.word_audio(item.vocab)
        await self.sentence_audio(item)


def asset_url(store: LocalStorage, a: Asset | None) -> str | None:
    if a is None or not a.storage_key:
        return None
    return store.url(a.storage_key)
