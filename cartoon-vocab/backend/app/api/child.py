"""孩子端接口（技术文档 5.2）。"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..lessons import package
from ..models import Attempt, Child, Episode, EpisodeStatus, LearningSession, Mastery, StickerAward, VocabItem, utcnow
from ..progress.scheduler import update_mastery
from .deps import current_child, get_episode, today

router = APIRouter(prefix="/api/v1")


def todays_episode(db: Session, child: Child) -> Episode | None:
    d = today()
    q = (select(Episode).where(Episode.child_id == child.id, Episode.status == EpisodeStatus.READY,
                               Episode.planned_date <= d)
         .order_by(Episode.planned_date.desc(), Episode.updated_at.desc()).limit(1))
    return db.scalars(q).first()


@router.get("/home")
def home(db: Session = Depends(get_db), child: Child = Depends(current_child)):
    ep = todays_episode(db, child)
    d = today()
    spaced_due = len(package.due_items(db, child.id, d, exclude={i.vocab_item_id for i in ep.items} if ep else set()))
    stickers = db.scalars(select(StickerAward).where(StickerAward.child_id == child.id)).all()
    return {
        "child": {"nickname": child.nickname, "avatar": child.avatar},
        "episode": None if ep is None else {
            "id": ep.id, "show_name": ep.show_name,
            "theme_color": package.theme_color(ep.show_name),
            "preview_done": package.did_finish(db, child.id, ep.id, "preview"),
            "review_done": package.did_finish(db, child.id, ep.id, "review"),
        },
        "spaced_available": spaced_due >= 2,
        "sticker_count": len(stickers),
        "voices": package.system_voice_entries(package.storage),
    }


@router.get("/lessons/spaced")
def spaced_lesson(db: Session = Depends(get_db), child: Child = Depends(current_child)):
    pkg = package.build_spaced_lesson(db, child.id, child.accent_pref, today())
    if pkg is None:
        raise HTTPException(404, "今天没有需要复习的词")
    return pkg


@router.get("/lessons/{episode_id}")
def episode_lesson(mode: str, ep: Episode = Depends(get_episode), db: Session = Depends(get_db),
                   child: Child = Depends(current_child)):
    if mode not in ("preview", "review"):
        raise HTTPException(422, "mode 只能是 preview 或 review")
    if ep.status != EpisodeStatus.READY:
        raise HTTPException(409, "课程还没准备好")
    return package.build_episode_lesson(db, ep, mode, child.id, child.accent_pref, today())


class SessionIn(BaseModel):
    episode_id: str | None = None
    mode: str = Field(pattern="^(preview|review|spaced)$")


@router.post("/sessions", status_code=201)
def start_session(body: SessionIn, db: Session = Depends(get_db), child: Child = Depends(current_child)):
    if body.episode_id:
        ep = db.get(Episode, body.episode_id)
        if ep is None or ep.child_id != child.id:
            raise HTTPException(404, "剧集不存在")
    s = LearningSession(child_id=child.id, episode_id=body.episode_id, mode=body.mode)
    db.add(s)
    db.commit()
    return {"id": s.id}


class AttemptIn(BaseModel):
    client_attempt_id: str = Field(min_length=8, max_length=64)
    vocab_item_id: str
    question_type: str = Field(pattern="^Q[2-5]$")
    option_ids: list[str] = []
    chosen_id: str
    is_correct: bool
    is_first_try: bool
    latency_ms: int = Field(default=0, ge=0)


def _session(db: Session, child: Child, session_id: str) -> LearningSession:
    s = db.get(LearningSession, session_id)
    if s is None or s.child_id != child.id:
        raise HTTPException(404, "学习记录不存在")
    return s


@router.post("/sessions/{session_id}/attempts")
def post_attempts(session_id: str, body: list[AttemptIn], db: Session = Depends(get_db),
                  child: Child = Depends(current_child)):
    s = _session(db, child, session_id)
    existing = set(db.scalars(select(Attempt.client_attempt_id).where(
        Attempt.client_attempt_id.in_([a.client_attempt_id for a in body]))).all())
    valid_vocab = set(db.scalars(select(VocabItem.id).where(VocabItem.id.in_({a.vocab_item_id for a in body}))).all())
    added = 0
    for a in body:
        if a.client_attempt_id in existing or a.vocab_item_id not in valid_vocab:
            continue  # 幂等：离线补传的重复记录直接跳过
        db.add(Attempt(session_id=s.id, **a.model_dump()))
        existing.add(a.client_attempt_id)
        added += 1
    db.commit()
    return {"accepted": added}


@router.post("/sessions/{session_id}/finish")
def finish_session(session_id: str, db: Session = Depends(get_db), child: Child = Depends(current_child)):
    s = _session(db, child, session_id)
    award = db.scalars(select(StickerAward).where(StickerAward.session_id == s.id)).first()
    if s.finished_at is None:
        s.finished_at = utcnow()
        d = today()
        per_item: dict[str, bool] = {}
        for a in db.scalars(select(Attempt).where(Attempt.session_id == s.id, Attempt.is_first_try.is_(True))
                            .order_by(Attempt.created_at)).all():
            per_item[a.vocab_item_id] = per_item.get(a.vocab_item_id, True) and a.is_correct
        for vocab_id, ok in per_item.items():
            m = db.get(Mastery, (child.id, vocab_id))
            if m is None:
                m = Mastery(child_id=child.id, vocab_item_id=vocab_id, streak_days=[])
                db.add(m)
            update_mastery(m, ok, d)
        ep = db.get(Episode, s.episode_id) if s.episode_id else None
        seed = package.stable_int(ep.show_name if ep else "spaced")
        award = StickerAward(child_id=child.id, session_id=s.id,
                             sticker_key=package.STICKERS[(seed + len(per_item)) % len(package.STICKERS)])
        db.add(award)
        db.commit()
    return {"sticker_key": award.sticker_key if award else None, "streak_days": _streak(db, child)}


def _streak(db: Session, child: Child) -> int:
    days = {f.date() for f in db.scalars(select(LearningSession.finished_at).where(
        LearningSession.child_id == child.id, LearningSession.finished_at.is_not(None))).all()}
    d, n = today(), 0
    while d in days:
        n += 1
        d -= timedelta(days=1)
    return n


@router.get("/stickers")
def stickers(db: Session = Depends(get_db), child: Child = Depends(current_child)):
    rows = db.scalars(select(StickerAward).where(StickerAward.child_id == child.id)
                      .order_by(StickerAward.created_at)).all()
    return [{"sticker_key": r.sticker_key, "created_at": r.created_at.isoformat()} for r in rows]
