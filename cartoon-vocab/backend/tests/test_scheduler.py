from datetime import date, timedelta

from app.models import Mastery
from app.progress.scheduler import is_weak, update_mastery

D0 = date(2026, 10, 1)


def new():
    return Mastery(child_id="c", vocab_item_id="v", streak_days=[], correct_streak=0, wrong_count=0, review_stage=0)


def test_first_learning_schedules_day_one():
    m = update_mastery(new(), True, D0)
    assert m.status == "learning" and m.next_due_at == D0 + timedelta(days=1)


def test_review_intervals_1_3_7_then_done():
    m = update_mastery(new(), True, D0)
    m = update_mastery(m, True, D0 + timedelta(days=1))
    assert m.next_due_at == D0 + timedelta(days=3)
    m = update_mastery(m, True, D0 + timedelta(days=3))
    assert m.next_due_at == D0 + timedelta(days=7)
    m = update_mastery(m, True, D0 + timedelta(days=7))
    assert m.next_due_at is None
    assert m.status == "mastered"


def test_mastery_needs_three_different_days():
    m = new()
    for _ in range(3):
        m = update_mastery(m, True, D0)
    assert m.status == "learning"


def test_wrong_answer_resets_and_reschedules_tomorrow():
    m = update_mastery(new(), True, D0)
    m = update_mastery(m, True, D0 + timedelta(days=1))
    m = update_mastery(m, False, D0 + timedelta(days=3))
    assert m.correct_streak == 0 and m.next_due_at == D0 + timedelta(days=4)
    m = update_mastery(m, False, D0 + timedelta(days=4))
    assert is_weak(m)
