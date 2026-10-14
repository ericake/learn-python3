"""选词入口：规则打分 →（可选）Claude 精选 → 校验。"""

import logging
import re

from ..config import settings
from .candidates import Candidate, lemmatize, phrase_candidates, word_candidates
from .lexicon import PHRASE_LEXICON, VISUAL_LEXICON
from .schemas import ExtractedItem, ExtractionResult

log = logging.getLogger(__name__)

_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def phrase_quota(n: int) -> int:
    return min(3, max(2, n // 4))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z' ]", "", s.lower()).strip()


def find_sentence(text: str, sentences: list[str]) -> str | None:
    """找出包含该词（任意词形）或短语的最短原句。"""
    target = [lemmatize(t) for t in _WORD.findall(text.lower())]
    if not target:
        return None
    hits = []
    for s in sentences:
        lemmas = [lemmatize(t) for t in _WORD.findall(s.lower())]
        n = len(target)
        if any(lemmas[i : i + n] == target for i in range(len(lemmas) - n + 1)):
            hits.append(s)
    return min(hits, key=len) if hits else None


def _image_prompt(text: str, type_: str) -> str:
    if type_ == "verb":
        return f"a cute cartoon animal clearly doing the action '{text}'"
    if type_ == "adj":
        return f"a simple object that is clearly {text}"
    if type_ == "phrase":
        return f"a simple scene clearly showing '{text}'"
    return f"a single {text}"


def _from_candidate(c: Candidate, sentences: list[str]) -> ExtractedItem:
    lex = VISUAL_LEXICON.get(c.text)
    reason = f"出现 {c.freq} 次" + ("，易于图示" if (lex or c.text in PHRASE_LEXICON) else "")
    return ExtractedItem(
        text=c.text,
        type=c.type,  # type: ignore[arg-type]
        meaning_zh=c.meaning_zh,
        source_sentence=find_sentence(c.text, sentences) or (sentences[c.sentence_idx[0]] if c.sentence_idx else ""),
        image_prompt=_image_prompt(c.text, c.type),
        emoji=c.emoji or "⭐",
        visualizability=5 if c.emoji else 2,
        reason=reason,
    )


def offline_extract(sentences: list[str], words: list[Candidate], phrases: list[Candidate], n: int) -> ExtractionResult:
    n_phr = min(phrase_quota(n), len(phrases))
    picked_phr = phrases[:n_phr]
    # 优先可视化的词；不足时再用其他高分词
    visual = [w for w in words if w.emoji]
    other = [w for w in words if not w.emoji]
    ordered = visual + other
    picked_words = ordered[: n - n_phr]
    rest = ordered[n - n_phr :] + phrases[n_phr:]
    return ExtractionResult(
        selected=[_from_candidate(c, sentences) for c in picked_words + picked_phr],
        backups=[_from_candidate(c, sentences) for c in rest[:8]],
    )


def validate_items(items: list[ExtractedItem], sentences: list[str], allow_unseen: bool = False) -> list[ExtractedItem]:
    """技术文档 6.2 的输出校验：原句可回溯、词出现在台词中、去重。"""
    norm_sentences = {_norm(s): s for s in sentences}
    out: list[ExtractedItem] = []
    seen: set[tuple[str, str]] = set()
    for it in items:
        key = (" ".join(lemmatize(t) for t in _WORD.findall(it.text.lower())), it.type)
        if not key[0] or key in seen:
            continue
        found = find_sentence(it.text, sentences)
        if found is None and not allow_unseen:
            log.info("drop item not in transcript: %s", it.text)
            continue
        if _norm(it.source_sentence) not in norm_sentences:
            it = it.model_copy(update={"source_sentence": found or it.source_sentence})
        else:
            it = it.model_copy(update={"source_sentence": norm_sentences[_norm(it.source_sentence)]})
        seen.add(key)
        out.append(it)
    return out


async def extract(show: str, sentences: list[str], mastered: set[str], n: int) -> tuple[ExtractionResult, str]:
    """返回 (结果, 使用的方式 llm/offline)。"""
    words = word_candidates(sentences, mastered)
    phrases = phrase_candidates(sentences, mastered)
    result, mode = None, "offline"
    if settings.use_llm:
        try:
            from .llm import llm_extract

            result = await llm_extract(show, sentences, words, phrases, sorted(mastered), n)
            mode = "llm"
        except Exception:  # LLM 不可用或拒答时退回规则提取，不阻塞家长
            log.exception("LLM extraction failed; falling back to offline extraction")
    if result is None:
        result = offline_extract(sentences, words, phrases, n)

    selected = validate_items(result.selected, sentences)
    backups = [b for b in validate_items(result.backups, sentences)
               if (b.text.lower(), b.type) not in {(s.text.lower(), s.type) for s in selected}]
    # 可视化评分过低的挪到备选
    low = [s for s in selected if s.visualizability < 3]
    selected = [s for s in selected if s.visualizability >= 3]
    backups = [b for b in backups if b.visualizability >= 3] + low + [b for b in backups if b.visualizability < 3]
    # 正选不足时用备选补齐（优先可视化评分高的）
    while len(selected) < n and backups:
        selected.append(backups.pop(0))
    return ExtractionResult(selected=selected[:n], backups=backups[:8]), mode
