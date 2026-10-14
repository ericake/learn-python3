"""课程编排（PRD F7 / F8 / F10，技术文档 6.5）。

纯函数：输入条目与干扰项池，输出题目序列。题目顺序、选项位置都在这里随机决定，
写进课程包，前端只按顺序播放，便于复现问题。
"""

import random
from dataclasses import dataclass

TYPE_ORDER = {"noun": 0, "verb": 1, "adj": 2, "other": 3, "phrase": 4}
STEP_SECONDS = {"intro": 4, "Q1": 10, "Q2": 7, "Q3": 8, "Q4": 10, "Q5": 8, "warmup": 3, "outro": 5}
MAX_LESSON_SECONDS = 8 * 60
MAX_SPACED_EXTRAS = 3


@dataclass(frozen=True)
class LessonItem:
    vocab_id: str
    text: str
    type: str
    image: str
    audio_n: str
    audio_s: str
    sentence_audio: str | None = None
    weak: bool = False

    @property
    def is_phrase(self) -> bool:
        return self.type == "phrase"


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _tokens(text: str) -> set[str]:
    return {t for t in text.lower().replace("'", " ").split() if len(t) > 2}


def overlaps(a: str, b: str) -> bool:
    """共享实词（如 puddle / muddy puddle、jump / jump up and down）的两个条目，图片往往相近，不能互为干扰项。"""
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta & tb) or any(x.startswith(y) or y.startswith(x) for x in ta for y in tb if min(len(x), len(y)) >= 3)


def sounds_similar(a: str, b: str) -> bool:
    a, b = a.lower(), b.lower()
    return a != b and len(a) > 1 and len(b) > 1 and _edit_distance(a, b) <= 1


class _Positioner:
    """随机选项位置，保证正确答案不会连续 3 题出现在同一位置。"""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.history: list[int] = []

    def arrange(self, answer: str, distractors: list[str]) -> list[str]:
        options = [answer, *distractors]
        self.rng.shuffle(options)
        pos = options.index(answer)
        if len(self.history) >= 2 and self.history[-1] == self.history[-2] == pos and len(options) > 1:
            new_pos = self.rng.choice([i for i in range(len(options)) if i != pos])
            options[pos], options[new_pos] = options[new_pos], options[pos]
            pos = new_pos
        self.history.append(pos)
        return options


class LessonBuilder:
    def __init__(self, items: list[LessonItem], pool: list[LessonItem] = (), seed: int | None = None):
        self.items = items
        self.pool = [p for p in pool if p.vocab_id not in {i.vocab_id for i in items}]
        self.rng = random.Random(seed)
        self.pos = _Positioner(self.rng)

    # ---------- 干扰项 ----------
    def _distractors(self, answer: LessonItem, k: int, *, phrase: bool, strict_sound: bool,
                     candidates: list[LessonItem] | None = None) -> list[str]:
        same_kind = [i for i in (candidates if candidates is not None else self.items)
                     if i.vocab_id != answer.vocab_id and i.is_phrase == phrase and i.image != answer.image]
        others = [i for i in self.items + self.pool
                  if i.vocab_id != answer.vocab_id and i.image != answer.image and i not in same_kind]
        picked: list[str] = []
        for group in (same_kind, others):
            group = list(group)
            self.rng.shuffle(group)
            for c in group:
                if len(picked) >= k:
                    break
                if strict_sound and sounds_similar(c.text, answer.text):
                    continue
                if overlaps(c.text, answer.text):
                    continue
                if c.image not in picked:
                    picked.append(c.image)
        return picked

    def _choice_step(self, qtype: str, item: LessonItem, prompt: list[str], k: int, *, strict_sound: bool,
                     candidates: list[LessonItem] | None = None) -> dict | None:
        ds = self._distractors(item, k, phrase=item.is_phrase, strict_sound=strict_sound, candidates=candidates)
        if not ds:
            return None  # 只有一个条目时无法出选择题
        return {"type": qtype, "item": item.vocab_id, "prompt": prompt,
                "options": self.pos.arrange(item.image, ds), "answer": item.image}

    @staticmethod
    def _q1(item: LessonItem) -> dict:
        return {"type": "Q1", "item": item.vocab_id, "image": item.image, "audio": [item.audio_n, item.audio_s]}

    @staticmethod
    def estimate_seconds(steps: list[dict]) -> int:
        return sum(STEP_SECONDS.get(s["type"], 5) * (len(s.get("items", [])) or 1) for s in steps)

    # ---------- 预习 ----------
    def preview(self) -> list[dict]:
        ordered = sorted(self.items, key=lambda i: (TYPE_ORDER.get(i.type, 3), i.text))
        words = [i for i in ordered if not i.is_phrase]
        phrases = [i for i in ordered if i.is_phrase]
        steps: list[dict] = [{"type": "intro", "voice": ["sys:today_we_watch", "sys:lets_learn"]}]
        steps += [self._q1(i) for i in ordered]
        q2 = [s for i in words if (s := self._choice_step("Q2", i, ["sys:where_is", i.audio_n], 1, strict_sound=True))]
        shuffled = list(words)
        self.rng.shuffle(shuffled)
        q3 = [s for i in shuffled if (s := self._choice_step("Q3", i, [i.audio_n], 3, strict_sound=True))]
        q5 = [s for i in phrases if (s := self._choice_step("Q5", i, [i.audio_n], 2, strict_sound=False))]
        outro = {"type": "outro", "voice": ["sys:now_lets_watch"], "sticker": True}
        # 超时先减少二选一，不减少四选一
        while q2 and self.estimate_seconds(steps + q2 + q3 + q5 + [outro]) > MAX_LESSON_SECONDS:
            q2.pop()
        return steps + q2 + q3 + q5 + [outro]

    # ---------- 复习 ----------
    def review(self, did_preview: bool, extras: list[LessonItem] = ()) -> list[dict]:
        extras = sorted(extras, key=lambda e: not e.weak)[:MAX_SPACED_EXTRAS]
        words = [i for i in self.items if not i.is_phrase]
        phrases = [i for i in self.items if i.is_phrase]
        steps: list[dict] = [{"type": "intro", "voice": ["sys:lets_review"]}]
        if not did_preview:
            # 没做预习：先用认识卡（图 + 读音 1 遍）代替快速闪现
            steps += [{"type": "Q1", "item": i.vocab_id, "image": i.image, "audio": [i.audio_n]} for i in self.items]
        else:
            steps.append({"type": "warmup",
                          "items": [{"item": i.vocab_id, "image": i.image, "audio": i.audio_n} for i in self.items]})
        q3_items = words + list(extras)
        self.rng.shuffle(q3_items)
        # 复习阶段干扰项可以更相近：优先同集同类型
        steps += [s for i in q3_items if (s := self._choice_step(
            "Q3", i, [i.audio_n], 3, strict_sound=False,
            candidates=[w for w in q3_items if w.type == i.type] or None))]
        q4_items = [i for i in words if i.sentence_audio]
        self.rng.shuffle(q4_items)
        steps += [s for i in q4_items if (s := self._choice_step("Q4", i, [i.sentence_audio], 3, strict_sound=False))]
        steps += [s for i in phrases if (s := self._choice_step("Q5", i, [i.audio_n], 2, strict_sound=False))]
        steps.append({"type": "outro", "voice": ["sys:sticker"], "sticker": True})
        while self.estimate_seconds(steps) > MAX_LESSON_SECONDS and any(s["type"] == "Q4" for s in steps):
            last_q4 = max(i for i, s in enumerate(steps) if s["type"] == "Q4")
            steps.pop(last_q4)
        return steps

    # ---------- 小复习 ----------
    def spaced(self) -> list[dict]:
        items = sorted(self.items, key=lambda e: not e.weak)
        steps: list[dict] = [{"type": "intro", "voice": ["sys:lets_review"]}]
        steps += [s for i in items if (s := self._choice_step("Q3", i, [i.audio_n], 3, strict_sound=False))]
        steps.append({"type": "outro", "voice": ["sys:sticker"], "sticker": True})
        return steps
