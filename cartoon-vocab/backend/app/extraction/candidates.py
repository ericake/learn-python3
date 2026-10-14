"""规则层：候选词与候选短语打分（技术文档 6.1）。

只负责缩小范围、给出排序依据；配置了 Claude 时最终选择由 LLM 完成，
否则直接取规则得分最高的条目（离线兜底）。
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from wordfreq import zipf_frequency

from .lexicon import PHRASE_LEXICON, STOPWORDS, VISUAL_LEXICON

_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

IRREGULAR = {
    "ran": "run", "went": "go", "fell": "fall", "flew": "fly", "ate": "eat", "drank": "drink",
    "swam": "swim", "sang": "sing", "slept": "sleep", "wore": "wear", "rode": "ride", "threw": "throw",
    "caught": "catch", "hid": "hide", "drew": "draw", "built": "build", "children": "child",
    "feet": "foot", "teeth": "tooth", "mice": "mouse", "men": "man", "women": "woman", "leaves": "leaf",
}


def _z(word: str) -> float:
    return zipf_frequency(word, "en")


def lemmatize(word: str) -> str:
    """轻量词形还原：只在还原后的形式是常见词时才采用。"""
    w = word.lower()
    if w in IRREGULAR:
        return IRREGULAR[w]
    if w in VISUAL_LEXICON:
        return w
    options: list[str] = []
    if w.endswith("ies") and len(w) > 4:
        options.append(w[:-3] + "y")
    if w.endswith("ing") and len(w) > 5:
        stem = w[:-3]
        options += [stem, stem + "e"]
        if len(stem) > 2 and stem[-1] == stem[-2]:
            options.append(stem[:-1])
    if w.endswith("ed") and len(w) > 4:
        stem = w[:-2]
        options += [stem, w[:-1]]
        if len(stem) > 2 and stem[-1] == stem[-2]:
            options.append(stem[:-1])
    if w.endswith("es") and len(w) > 4:
        options.append(w[:-2])
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        options.append(w[:-1])
    base = _z(w)
    best, best_z = w, -1.0
    for o in options:
        if o in VISUAL_LEXICON:
            return o
        zo = _z(o)
        if zo >= max(3.0, base - 0.5) and zo > best_z:
            best, best_z = o, zo
    return best


@dataclass
class Candidate:
    text: str  # 原形（短语保持原样小写）
    type: str
    freq: int
    score: float
    sentence_idx: list[int] = field(default_factory=list)
    surface: str = ""  # 台词中最常见的原始形态
    emoji: str | None = None
    meaning_zh: str = ""

    @property
    def is_phrase(self) -> bool:
        return self.type == "phrase"


def _difficulty_fit(z: float) -> float:
    # Zipf 4.0~6.0 的常用词最适合 6 岁启蒙；太罕见或太基础都降权
    if 4.0 <= z <= 6.0:
        return 1.0
    return max(0.0, 1.0 - abs(z - (4.0 if z < 4.0 else 6.0)) / 2)


def word_candidates(sentences: list[str], mastered: set[str] = frozenset(), keep_names: bool = False) -> list[Candidate]:
    counts: Counter[str] = Counter()
    surfaces: dict[str, Counter[str]] = {}
    where: dict[str, list[int]] = {}
    # 专有名词（人名/角色名）：在句中出现过大写形式、且从未以小写出现的词
    upper_mid, lower_any = set(), set()
    for sent in sentences:
        for j, m in enumerate(_WORD.finditer(sent)):
            tok = m.group(0)
            if tok[0].isupper() and j > 0:
                upper_mid.add(tok.lower())
            elif tok[0].islower():
                lower_any.add(tok)
    names = set() if keep_names else (upper_mid - lower_any) - set(VISUAL_LEXICON)
    for i, sent in enumerate(sentences):
        for m in _WORD.finditer(sent):
            tok = m.group(0)
            low = tok.lower()
            if low in STOPWORDS or len(low) <= 2 or "'" in low or low in names:
                continue
            lemma = lemmatize(low)
            if lemma in STOPWORDS:
                continue
            counts[lemma] += 1
            surfaces.setdefault(lemma, Counter())[low] += 1
            where.setdefault(lemma, [])
            if i not in where[lemma]:
                where[lemma].append(i)

    # 首句出现的词（通常是剧集情境）加权
    first = set(lemmatize(t.lower()) for t in _WORD.findall(" ".join(sentences[:2])))
    out = []
    for lemma, freq in counts.items():
        lex = VISUAL_LEXICON.get(lemma)
        visual = 1.0 if lex else 0.15
        score = (
            1.0 * math.log1p(freq)
            + 1.6 * visual
            + 0.6 * _difficulty_fit(_z(lemma))
            + (0.3 if lemma in first else 0.0)
            - (2.0 if lemma in mastered else 0.0)
        )
        out.append(
            Candidate(
                text=lemma,
                type=lex[0] if lex else "other",
                freq=freq,
                score=round(score, 3),
                sentence_idx=where[lemma],
                surface=surfaces[lemma].most_common(1)[0][0],
                emoji=lex[1] if lex else None,
                meaning_zh=lex[2] if lex else "",
            )
        )
    out.sort(key=lambda c: (-c.score, c.text))
    return out


def _phrase_key(toks: list[str]) -> str:
    return " ".join(t if t in STOPWORDS else lemmatize(t) for t in toks)


def phrase_candidates(sentences: list[str], mastered: set[str] = frozenset()) -> list[Candidate]:
    counts: Counter[str] = Counter()
    surfaces: dict[str, Counter[str]] = {}
    where: dict[str, list[int]] = {}
    for i, sent in enumerate(sentences):
        toks = [t.lower() for t in _WORD.findall(sent)]
        seen: set[str] = set()
        for n in (2, 3, 4):
            for k in range(len(toks) - n + 1):
                window = toks[k : k + n]
                surface = " ".join(window)
                key = _phrase_key(window)
                known = surface in PHRASE_LEXICON or key in PHRASE_LEXICON
                content = [t for t in window if t not in STOPWORDS]
                ok_edges = window[0] not in {"the", "a", "an", "and", "of", "in"} and window[-1] not in {
                    "the", "a", "an", "and", "to", "of", "in", "your", "my", "his", "her", "their"}
                if (known or (content and ok_edges)) and key not in seen:
                    seen.add(key)
                    counts[key] += 1
                    surfaces.setdefault(key, Counter())[surface] += 1
                    where.setdefault(key, []).append(i)
    out = []
    for key, freq in counts.items():
        surface = surfaces[key].most_common(1)[0][0]
        lex = PHRASE_LEXICON.get(key) or PHRASE_LEXICON.get(surface)
        if not lex and freq < 2:
            continue
        text = key if key in PHRASE_LEXICON else surface
        score = math.log1p(freq) + (2.0 if lex else 0.0) + 0.2 * len(key.split()) - (2.0 if text in mastered else 0.0)
        out.append(
            Candidate(
                text=text, type="phrase", freq=freq, score=round(score, 3), sentence_idx=where[key],
                surface=surface, emoji=lex[0] if lex else None, meaning_zh=lex[1] if lex else "",
            )
        )
    out.sort(key=lambda c: (-c.score, -len(c.text), c.text))
    # 去掉被更长短语包含、且出现次数不更多的短语
    kept: list[Candidate] = []
    for c in out:
        if any(c.text in k.text and c.freq <= k.freq for k in kept):
            continue
        kept.append(c)
    return kept
