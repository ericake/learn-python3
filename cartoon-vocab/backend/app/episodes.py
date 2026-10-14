"""剧集流程：提交台词 → 选词 → 家长审核 → 生成素材（技术文档 4.1 / 6）。

MVP 用进程内 asyncio 任务代替 arq 队列；任务函数自己开数据库会话，
以后迁移到独立 worker 时只需换调度方式。
"""

import asyncio
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import transcript
from .assets.service import AssetGenerator
from .config import settings
from .db import SessionLocal
from .extraction.candidates import lemmatize
from .extraction.lexicon import PHRASE_LEXICON, VISUAL_LEXICON
from .extraction.schemas import ExtractedItem
from .extraction.service import _image_prompt, extract, find_sentence
from .models import Episode, EpisodeItem, EpisodeStatus, Mastery, VocabItem

log = logging.getLogger(__name__)

_background: set[asyncio.Task] = set()


def spawn(coro) -> asyncio.Task:
    task = asyncio.get_running_loop().create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


def sentences_of(ep: Episode) -> list[str]:
    return [l["text"] for l in (ep.transcript_clean or [])]


def lemma_key(text: str, type_: str) -> str:
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text.lower())
    if type_ == "phrase":
        return " ".join(words)
    return " ".join(lemmatize(w) for w in words)


def get_or_create_vocab(db: Session, it: ExtractedItem, accent: str) -> VocabItem:
    lemma = lemma_key(it.text, it.type)
    v = db.scalars(select(VocabItem).where(VocabItem.lemma == lemma, VocabItem.type == it.type,
                                           VocabItem.accent == accent)).first()
    if v is None:
        v = VocabItem(text=it.text.strip(), lemma=lemma, type=it.type, accent=accent, emoji=it.emoji)
        db.add(v)
        db.flush()
    elif not v.emoji and it.emoji:
        v.emoji = it.emoji
    return v


def submit_transcript(db: Session, ep: Episode, text: str) -> None:
    lines = transcript.clean(text)
    transcript.validate(text, lines)
    ep.transcript_raw = text
    ep.transcript_clean = transcript.to_json(lines)
    ep.items.clear()
    ep.status = EpisodeStatus.EXTRACTING
    ep.error = None
    ep.progress = {"stage": "extract"}
    db.commit()


def _add_item(db: Session, ep: Episode, it: ExtractedItem, accent: str, *, selected: bool, order: int) -> EpisodeItem:
    vocab = get_or_create_vocab(db, it, accent)
    item = EpisodeItem(
        episode_id=ep.id, vocab_item_id=vocab.id, source_sentence=it.source_sentence, meaning_zh=it.meaning_zh,
        image_prompt=it.image_prompt, visualizability=it.visualizability, reason=it.reason,
        selected=selected, is_backup=not selected, sort_order=order,
    )
    item.vocab = vocab
    ep.items.append(item)
    return item


def mastered_lemmas(db: Session, child_id: str) -> set[str]:
    rows = db.execute(
        select(VocabItem.lemma).join(Mastery, Mastery.vocab_item_id == VocabItem.id)
        .where(Mastery.child_id == child_id, Mastery.status == "mastered")
    ).scalars()
    return set(rows)


async def run_extract(episode_id: str, session_factory: sessionmaker = SessionLocal) -> None:
    with session_factory() as db:
        ep = db.get(Episode, episode_id)
        if ep is None:
            return
        try:
            accent = ep_accent(db, ep)
            result, mode = await extract(ep.show_name, sentences_of(ep), mastered_lemmas(db, ep.child_id),
                                         ep.target_item_count)
            for i, it in enumerate(result.selected):
                _add_item(db, ep, it, accent, selected=True, order=i)
            for j, it in enumerate(result.backups):
                _add_item(db, ep, it, accent, selected=False, order=100 + j)
            ep.status = EpisodeStatus.REVIEWING
            ep.progress = {"stage": "review", "extractor": mode}
        except Exception as e:  # noqa: BLE001
            log.exception("extract failed for %s", episode_id)
            ep.status = EpisodeStatus.FAILED
            ep.error = f"选词失败：{e}"
        db.commit()


def ep_accent(db: Session, ep: Episode) -> str:
    from .models import Child

    child = db.get(Child, ep.child_id)
    return child.accent_pref if child else "en-GB"


async def add_manual_item(db: Session, ep: Episode, text: str) -> EpisodeItem:
    text = text.strip()
    sentences = sentences_of(ep)
    it: ExtractedItem | None = None
    if settings.use_llm:
        try:
            from .extraction.llm import llm_complete_item

            it = await llm_complete_item(ep.show_name, sentences, text)
        except Exception:  # noqa: BLE001
            log.exception("LLM completion failed; using offline fill")
    if it is None:
        is_phrase = len(text.split()) > 1
        lemma = text.lower() if is_phrase else lemmatize(text)
        lex = PHRASE_LEXICON.get(lemma) if is_phrase else VISUAL_LEXICON.get(lemma)
        type_ = "phrase" if is_phrase else (lex[0] if lex else "noun")
        it = ExtractedItem(
            text=text if is_phrase else lemma, type=type_,
            meaning_zh=(lex[1] if is_phrase else lex[2]) if lex else "",
            source_sentence=find_sentence(text, sentences) or "",
            image_prompt=_image_prompt(text, type_),
            emoji=(lex[0] if is_phrase else lex[1]) if lex else "⭐",
            visualizability=5 if lex else 3, reason="家长添加",
        )
    else:
        it = it.model_copy(update={"reason": it.reason or "家长添加",
                                   "source_sentence": find_sentence(it.text, sentences) or it.source_sentence})
    order = max((i.sort_order for i in ep.items if i.selected), default=-1) + 1
    item = _add_item(db, ep, it, ep_accent(db, ep), selected=True, order=order)
    db.commit()
    return item


async def run_generate(episode_id: str, session_factory: sessionmaker = SessionLocal,
                       generator_factory=AssetGenerator) -> None:
    with session_factory() as db:
        ep = db.get(Episode, episode_id)
        if ep is None:
            return
        items = [i for i in ep.items if i.selected]
        gen = generator_factory(db, episode_id=ep.id)
        ep.progress = {"stage": "assets", "done": 0, "total": len(items)}
        db.commit()
        done = 0

        async def one(item: EpisodeItem) -> None:
            nonlocal done
            try:
                await gen.all_for_item(item)
                item.asset_error = None
            except Exception as e:  # noqa: BLE001
                log.exception("asset generation failed for %s", item.vocab.text)
                item.asset_error = str(e)[:500]
            done += 1
            ep.progress = {"stage": "assets", "done": done, "total": len(items)}

        await asyncio.gather(*(one(i) for i in items))
        failed = [i.vocab.text for i in items if i.asset_error]
        if failed:
            ep.status = EpisodeStatus.FAILED
            ep.error = "以下条目素材生成失败，可重试：" + "、".join(failed)
        else:
            ep.status = EpisodeStatus.READY
            ep.error = None
            ep.progress = {"stage": "ready", "done": len(items), "total": len(items)}
        db.commit()
