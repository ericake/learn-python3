"""把数据库里的条目和素材组装成课程包（技术文档 5.3）。"""

import hashlib
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..assets.storage import LocalStorage, storage
from ..models import Asset, Episode, EpisodeItem, LearningSession, Mastery, VocabItem
from ..progress.scheduler import is_weak
from .builder import LessonBuilder, LessonItem
from .voices import PRAISE_KEYS, SYSTEM_VOICES

THEME_COLORS = ["#F7A1C4", "#9AD0F5", "#FFD166", "#B5E48C", "#CDB4DB", "#FFADAD"]
STICKERS = ["pig_boots", "puddle_splash", "rainbow", "teddy", "dinosaur", "rocket", "ice_cream", "star"]


def stable_int(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest(), 16)


def theme_color(show_name: str) -> str:
    return THEME_COLORS[stable_int(show_name) % len(THEME_COLORS)]


def _lesson_item(vocab: VocabItem, image_id: str | None, sentence_audio: str | None, weak: bool = False) -> LessonItem | None:
    if not (image_id and vocab.audio_normal_id and vocab.audio_slow_id):
        return None
    return LessonItem(vocab_id=vocab.id, text=vocab.text, type=vocab.type, image=image_id,
                      audio_n=vocab.audio_normal_id, audio_s=vocab.audio_slow_id,
                      sentence_audio=sentence_audio, weak=weak)


def episode_lesson_items(ep: Episode) -> list[LessonItem]:
    out = []
    for it in ep.items:
        if it.selected and (li := _lesson_item(it.vocab, it.image_id, it.sentence_audio_id)):
            out.append(li)
    return out


def due_items(db: Session, child_id: str, today: date, exclude: set[str] = frozenset()) -> list[LessonItem]:
    rows = db.execute(
        select(Mastery, VocabItem).join(VocabItem, VocabItem.id == Mastery.vocab_item_id)
        .where(Mastery.child_id == child_id, Mastery.next_due_at.is_not(None), Mastery.next_due_at <= today)
    ).all()
    out = []
    for m, v in rows:
        if v.id in exclude:
            continue
        if li := _lesson_item(v, v.default_image_id, None, weak=is_weak(m)):
            out.append(li)
    out.sort(key=lambda i: (not i.weak, i.text))
    return out


def distractor_pool(db: Session, accent: str, limit: int = 40) -> list[LessonItem]:
    vs = db.scalars(select(VocabItem).where(VocabItem.accent == accent, VocabItem.default_image_id.is_not(None))
                    .limit(limit)).all()
    return [li for v in vs if (li := _lesson_item(v, v.default_image_id, None))]


def did_finish(db: Session, child_id: str, episode_id: str, mode: str) -> bool:
    return db.scalars(select(LearningSession.id).where(
        LearningSession.child_id == child_id, LearningSession.episode_id == episode_id,
        LearningSession.mode == mode, LearningSession.finished_at.is_not(None)).limit(1)).first() is not None


def _asset_entry(store: LocalStorage, a: Asset) -> dict:
    entry: dict = {"kind": a.kind}
    if a.storage_key:
        entry["url"] = store.url(a.storage_key)
    if a.kind == "audio":
        entry["speak_text"] = a.speak_text
        entry["rate"] = (a.params or {}).get("rate", 1.0)
        if a.duration_ms:
            entry["duration_ms"] = a.duration_ms
    return entry


def system_voice_entries(store: LocalStorage) -> dict:
    out = {}
    for key, text in SYSTEM_VOICES.items():
        entry: dict = {"kind": "audio", "speak_text": text, "rate": 1.0}
        if (store.root / "voice" / f"{key}.mp3").exists():
            entry["url"] = store.url(f"voice/{key}.mp3")
        out[f"sys:{key}"] = entry
    return out


def assemble(db: Session, *, lesson_id: str, mode: str, accent: str, steps: list[dict], items: list[LessonItem],
             episode: Episode | None, store: LocalStorage = storage) -> dict:
    ids: set[str] = set()
    for i in items:
        ids |= {i.image, i.audio_n, i.audio_s} | ({i.sentence_audio} if i.sentence_audio else set())
    for s in steps:
        for k in ("image", "answer"):
            if isinstance(s.get(k), str):
                ids.add(s[k])
        for k in ("audio", "prompt", "options"):
            ids |= set(s.get(k) or [])
        for w in s.get("items", []):
            ids |= {w["image"], w["audio"]}
    ids = {i for i in ids if not i.startswith("sys:")}
    assets = {a.id: _asset_entry(store, a) for a in db.scalars(select(Asset).where(Asset.id.in_(ids))).all()}
    assets.update(system_voice_entries(store))
    seed = stable_int(episode.show_name if episode else "spaced")
    return {
        "lesson_id": lesson_id,
        "episode_id": episode.id if episode else None,
        "mode": mode,
        "accent": accent,
        "theme": {"color": theme_color(episode.show_name if episode else "spaced"), "sticker_key": STICKERS[seed % len(STICKERS)]},
        "praise": [f"sys:{k}" for k in PRAISE_KEYS],
        "items": {i.vocab_id: {"image": i.image, "audio": i.audio_n, "type": i.type} for i in items},
        "assets": assets,
        "steps": steps,
    }


def build_episode_lesson(db: Session, ep: Episode, mode: str, child_id: str, accent: str, today: date,
                         seed: int | None = None) -> dict:
    items = episode_lesson_items(ep)
    pool = distractor_pool(db, accent)
    builder = LessonBuilder(items, pool, seed=seed)
    extras: list[LessonItem] = []
    if mode == "preview":
        steps = builder.preview()
    else:
        extras = due_items(db, child_id, today, exclude={i.vocab_id for i in items})[:3]
        steps = builder.review(did_preview=did_finish(db, child_id, ep.id, "preview"), extras=extras)
    return assemble(db, lesson_id=f"{ep.id}:{mode}", mode=mode, accent=accent, steps=steps,
                    items=items + extras, episode=ep)


def build_spaced_lesson(db: Session, child_id: str, accent: str, today: date, seed: int | None = None) -> dict | None:
    items = due_items(db, child_id, today)[:8]
    if len(items) < 2:
        return None
    builder = LessonBuilder(items, distractor_pool(db, accent), seed=seed)
    return assemble(db, lesson_id=f"spaced:{today.isoformat()}", mode="spaced", accent=accent,
                    steps=builder.spaced(), items=items, episode=None)


def episode_items_ready(items: list[EpisodeItem]) -> bool:
    return all(i.image_id and i.vocab.audio_normal_id and i.vocab.audio_slow_id for i in items if i.selected)
