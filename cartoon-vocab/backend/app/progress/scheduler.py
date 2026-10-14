"""掌握状态与间隔复习调度（PRD F9 / 技术文档 6.6）。

- 每节课里，一个条目的所有“首次选择”都答对，才算这节答对；
- 跨不同的天连续 3 次答对 → mastered；
- 首次学习后第 1、3、7 天进入复习；答错则明天再复习。
"""

from datetime import date, datetime, timedelta, timezone

from ..models import Mastery

REVIEW_OFFSETS = (1, 3, 7)
MASTERY_STREAK = 3


def update_mastery(m: Mastery, correct: bool, today: date, now: datetime | None = None) -> Mastery:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    if m.first_learned_on is None:
        m.first_learned_on = today
        m.review_stage = 0
        m.next_due_at = today + timedelta(days=REVIEW_OFFSETS[0])
    elif m.next_due_at is not None and today >= m.next_due_at and correct:
        # 按期完成了一次复习，进入下一个间隔
        m.review_stage = (m.review_stage or 0) + 1
        m.next_due_at = (m.first_learned_on + timedelta(days=REVIEW_OFFSETS[m.review_stage])
                         if m.review_stage < len(REVIEW_OFFSETS) else None)
        if m.next_due_at is not None and m.next_due_at <= today:
            m.next_due_at = today + timedelta(days=1)

    if correct:
        days = list(m.streak_days or [])
        if today.isoformat() not in days:
            days.append(today.isoformat())
        m.streak_days = days
        m.correct_streak = (m.correct_streak or 0) + 1
    else:
        m.correct_streak = 0
        m.streak_days = []
        m.wrong_count = (m.wrong_count or 0) + 1
        m.next_due_at = today + timedelta(days=1)

    if m.correct_streak >= MASTERY_STREAK and len(m.streak_days) >= MASTERY_STREAK:
        m.status = "mastered"
    else:
        m.status = "learning"
    m.last_seen_at = now
    return m


def is_weak(m: Mastery) -> bool:
    return (m.wrong_count or 0) >= 2 and m.status != "mastered"
