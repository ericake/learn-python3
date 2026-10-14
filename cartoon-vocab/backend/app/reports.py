"""家长报告（PRD F5 简版）。"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Attempt, Episode, LearningSession, Mastery, VocabItem
from .progress.scheduler import is_weak


def _streak(finished_days: set[date], today: date) -> int:
    n, d = 0, today
    while d in finished_days:
        n += 1
        d -= timedelta(days=1)
    return n


def summary(db: Session, child_id: str, today: date) -> dict:
    rows = db.execute(select(Mastery, VocabItem).join(VocabItem, VocabItem.id == Mastery.vocab_item_id)
                      .where(Mastery.child_id == child_id)).all()
    groups = {"mastered": [], "learning": [], "weak": []}
    for m, v in rows:
        entry = {"vocab_id": v.id, "text": v.text, "emoji": v.emoji, "wrong_count": m.wrong_count,
                 "next_due_at": m.next_due_at.isoformat() if m.next_due_at else None}
        if m.status == "mastered":
            groups["mastered"].append(entry)
        elif is_weak(m):
            groups["weak"].append(entry)
        else:
            groups["learning"].append(entry)
    finished = {f.date() for f in db.scalars(select(LearningSession.finished_at).where(
        LearningSession.child_id == child_id, LearningSession.finished_at.is_not(None))).all()}
    return {
        "streak_days": _streak(finished, today),
        "days_this_week": len({d for d in finished if d > today - timedelta(days=7)}),
        "counts": {k: len(v) for k, v in groups.items()},
        **{k: sorted(v, key=lambda e: e["text"]) for k, v in groups.items()},
    }


def episode_report(db: Session, child_id: str, ep: Episode) -> dict:
    sessions = db.scalars(select(LearningSession).where(LearningSession.child_id == child_id,
                                                        LearningSession.episode_id == ep.id)
                          .order_by(LearningSession.started_at)).all()
    modes = {}
    for mode in ("preview", "review"):
        done = [s for s in sessions if s.mode == mode and s.finished_at]
        modes[mode] = {
            "done": bool(done),
            "duration_sec": int((done[-1].finished_at - done[-1].started_at).total_seconds()) if done else None,
        }
    attempts = db.scalars(select(Attempt).where(Attempt.session_id.in_([s.id for s in sessions]),
                                                Attempt.is_first_try.is_(True))).all()
    per: dict[str, list[bool]] = {}
    for a in attempts:
        per.setdefault(a.vocab_item_id, []).append(a.is_correct)
    items = []
    for it in ep.items:
        if not it.selected:
            continue
        res = per.get(it.vocab_item_id, [])
        items.append({"vocab_id": it.vocab_item_id, "text": it.vocab.text, "emoji": it.vocab.emoji,
                      "first_try_correct": sum(res), "first_try_total": len(res)})
    return {"episode_id": ep.id, **modes, "items": items}
