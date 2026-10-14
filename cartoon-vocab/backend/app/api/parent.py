"""家长端接口（技术文档 5.1）。"""

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import episodes as flow
from .. import reports
from ..assets.service import AssetGenerator, asset_url
from ..assets.storage import storage
from ..db import get_db
from ..models import Asset, Child, Episode, EpisodeItem, EpisodeStatus, Mastery
from ..transcript import TranscriptError
from .deps import current_child, get_episode, today

router = APIRouter(prefix="/api/v1")


# ---------- 孩子档案 ----------
class ChildIn(BaseModel):
    nickname: str | None = Field(default=None, max_length=50)
    avatar: str | None = Field(default=None, max_length=50)
    accent_pref: str | None = Field(default=None, pattern="^en-(GB|US)$")


@router.get("/child")
def get_child(child: Child = Depends(current_child)):
    return {"id": child.id, "nickname": child.nickname, "avatar": child.avatar, "accent_pref": child.accent_pref}


@router.put("/child")
def put_child(body: ChildIn, db: Session = Depends(get_db), child: Child = Depends(current_child)):
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(child, k, v)
    db.commit()
    return get_child(child)


# ---------- 剧集 ----------
class EpisodeIn(BaseModel):
    show_name: str = Field(min_length=1, max_length=100)
    season: int | None = None
    episode_no: int | None = None
    title: str | None = Field(default=None, max_length=200)
    planned_date: date | None = None
    target_item_count: int = Field(default=10, ge=4, le=12)


class EpisodePatch(BaseModel):
    show_name: str | None = Field(default=None, min_length=1, max_length=100)
    season: int | None = None
    episode_no: int | None = None
    title: str | None = Field(default=None, max_length=200)
    planned_date: date | None = None
    target_item_count: int | None = Field(default=None, ge=4, le=12)


def _url(db: Session, asset_id: str | None) -> str | None:
    return asset_url(storage, db.get(Asset, asset_id)) if asset_id else None


def _speak(db: Session, asset_id: str | None) -> str | None:
    a = db.get(Asset, asset_id) if asset_id else None
    return a.speak_text if a else None


def item_out(db: Session, it: EpisodeItem) -> dict:
    v = it.vocab
    return {
        "id": it.id, "vocab_id": v.id, "text": v.text, "type": v.type, "emoji": v.emoji,
        "meaning_zh": it.meaning_zh, "source_sentence": it.source_sentence, "image_prompt": it.image_prompt,
        "visualizability": it.visualizability, "reason": it.reason, "selected": it.selected,
        "is_backup": it.is_backup, "sort_order": it.sort_order, "asset_error": it.asset_error,
        "image_url": _url(db, it.image_id), "image_regen_left": max(0, 3 - it.image_regen_count),
        "audio_normal_url": _url(db, v.audio_normal_id), "audio_slow_url": _url(db, v.audio_slow_id),
        "sentence_audio_url": _url(db, it.sentence_audio_id),
        "speak_text": v.text if v.audio_normal_id else None,
    }


def episode_out(ep: Episode, db: Session | None = None, with_items: bool = False) -> dict:
    out = {
        "id": ep.id, "show_name": ep.show_name, "season": ep.season, "episode_no": ep.episode_no,
        "title": ep.title, "status": ep.status, "planned_date": ep.planned_date.isoformat(),
        "target_item_count": ep.target_item_count, "error": ep.error, "progress": ep.progress or {},
        "has_transcript": bool(ep.transcript_raw), "sentence_count": len(ep.transcript_clean or []),
        "selected_count": sum(1 for i in ep.items if i.selected),
    }
    if with_items and db is not None:
        out["items"] = [item_out(db, i) for i in sorted(ep.items, key=lambda i: (not i.selected, i.sort_order))]
    return out


@router.get("/episodes")
def list_episodes(status: str | None = None, db: Session = Depends(get_db), child: Child = Depends(current_child)):
    q = select(Episode).where(Episode.child_id == child.id).order_by(Episode.planned_date.desc(), Episode.created_at.desc())
    if status:
        q = q.where(Episode.status == status)
    return [episode_out(e) for e in db.scalars(q).all()]


@router.post("/episodes", status_code=201)
def create_episode(body: EpisodeIn, db: Session = Depends(get_db), child: Child = Depends(current_child)):
    data = body.model_dump()
    data["planned_date"] = data["planned_date"] or today()
    ep = Episode(child_id=child.id, **data)
    db.add(ep)
    db.commit()
    return episode_out(ep)


@router.get("/episodes/{episode_id}")
def get_episode_detail(ep: Episode = Depends(get_episode), db: Session = Depends(get_db)):
    return episode_out(ep, db, with_items=True)


@router.patch("/episodes/{episode_id}")
def update_episode(body: EpisodePatch, ep: Episode = Depends(get_episode), db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(ep, k, v)
    db.commit()
    return episode_out(ep)


@router.delete("/episodes/{episode_id}", status_code=204)
def delete_episode(ep: Episode = Depends(get_episode), db: Session = Depends(get_db)):
    db.delete(ep)
    db.commit()


def _guard_not_busy(ep: Episode) -> None:
    if ep.status in (EpisodeStatus.EXTRACTING, EpisodeStatus.GENERATING):
        raise HTTPException(409, "正在处理中，请稍候")


@router.put("/episodes/{episode_id}/transcript", status_code=202)
async def put_transcript(
    text: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    ep: Episode = Depends(get_episode),
    db: Session = Depends(get_db),
):
    _guard_not_busy(ep)
    if file is not None:
        raw = await file.read()
        text = raw.decode("utf-8-sig", errors="replace")
    if not text or not text.strip():
        raise HTTPException(422, "请粘贴台词或上传字幕文件")
    try:
        flow.submit_transcript(db, ep, text)
    except TranscriptError as e:
        raise HTTPException(422, str(e)) from e
    flow.spawn(flow.run_extract(ep.id))
    return episode_out(ep)


class ItemPatch(BaseModel):
    selected: bool | None = None
    source_sentence: str | None = None
    meaning_zh: str | None = None
    image_prompt: str | None = None


@router.patch("/episodes/{episode_id}/items/{item_id}")
def patch_item(item_id: str, body: ItemPatch, ep: Episode = Depends(get_episode), db: Session = Depends(get_db)):
    _guard_not_busy(ep)
    it = next((i for i in ep.items if i.id == item_id), None)
    if it is None:
        raise HTTPException(404, "条目不存在")
    data = body.model_dump(exclude_unset=True)
    if data.get("selected") and not it.selected:
        if sum(1 for i in ep.items if i.selected) >= 12:
            raise HTTPException(422, "每集最多 12 个条目")
        it.sort_order = max((i.sort_order for i in ep.items if i.selected), default=-1) + 1
    if "source_sentence" in data and data["source_sentence"] != it.source_sentence:
        it.sentence_audio_id = None  # 原句改了，音频需要重新生成
    if "image_prompt" in data and data["image_prompt"] != it.image_prompt:
        it.image_id = None
    for k, v in data.items():
        setattr(it, k, v)
    db.commit()
    return item_out(db, it)


class NewItem(BaseModel):
    text: str = Field(min_length=1, max_length=60)


@router.post("/episodes/{episode_id}/items", status_code=201)
async def add_item(body: NewItem, ep: Episode = Depends(get_episode), db: Session = Depends(get_db)):
    _guard_not_busy(ep)
    if not ep.transcript_clean:
        raise HTTPException(422, "请先提交台词")
    if sum(1 for i in ep.items if i.selected) >= 12:
        raise HTTPException(422, "每集最多 12 个条目")
    it = await flow.add_manual_item(db, ep, body.text)
    return item_out(db, it)


@router.post("/episodes/{episode_id}/confirm", status_code=202)
async def confirm(ep: Episode = Depends(get_episode), db: Session = Depends(get_db)):
    _guard_not_busy(ep)
    n = sum(1 for i in ep.items if i.selected)
    if not 4 <= n <= 12:
        raise HTTPException(422, f"请选择 4～12 个条目（当前 {n} 个）")
    ep.status = EpisodeStatus.GENERATING
    ep.error = None
    db.commit()
    flow.spawn(flow.run_generate(ep.id))
    return episode_out(ep)


@router.post("/episodes/{episode_id}/items/{item_id}/regenerate-image")
async def regenerate_image(item_id: str, ep: Episode = Depends(get_episode), db: Session = Depends(get_db)):
    it = next((i for i in ep.items if i.id == item_id), None)
    if it is None:
        raise HTTPException(404, "条目不存在")
    try:
        await AssetGenerator(db, episode_id=ep.id).regenerate_image(it)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    db.commit()
    return item_out(db, it)


@router.post("/episodes/{episode_id}/items/{item_id}/image")
async def upload_image(item_id: str, file: UploadFile = File(...), ep: Episode = Depends(get_episode),
                       db: Session = Depends(get_db)):
    it = next((i for i in ep.items if i.id == item_id), None)
    if it is None:
        raise HTTPException(404, "条目不存在")
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(file.content_type or "")
    if ext is None:
        raise HTTPException(422, "只支持 PNG / JPEG / WebP 图片")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(422, "图片不能超过 5MB")
    import hashlib

    h = hashlib.sha256(data).hexdigest()
    key = storage.put(f"image/upload/{h}.{ext}", data)
    a = Asset(kind="image", provider="upload", storage_key=key, mime=file.content_type, bytes=len(data), content_hash=h)
    db.add(a)
    db.flush()
    it.image_id = a.id
    it.vocab.default_image_id = a.id
    db.commit()
    return item_out(db, it)


# ---------- 报告 ----------
@router.get("/reports/summary")
def report_summary(db: Session = Depends(get_db), child: Child = Depends(current_child)):
    return reports.summary(db, child.id, today())


@router.get("/reports/episodes/{episode_id}")
def report_episode(ep: Episode = Depends(get_episode), db: Session = Depends(get_db), child: Child = Depends(current_child)):
    return reports.episode_report(db, child.id, ep)


@router.post("/reports/weak/{vocab_id}/tomorrow")
def weak_to_tomorrow(vocab_id: str, db: Session = Depends(get_db), child: Child = Depends(current_child)):
    from datetime import timedelta

    m = db.get(Mastery, (child.id, vocab_id))
    if m is None:
        raise HTTPException(404, "没有这个词的学习记录")
    m.next_due_at = today() + timedelta(days=1)
    db.commit()
    return {"ok": True, "next_due_at": m.next_due_at.isoformat()}
