import asyncio

from conftest import SAMPLE

from app.extraction.candidates import lemmatize, phrase_candidates, word_candidates
from app.extraction.schemas import ExtractedItem
from app.extraction.service import extract, find_sentence, validate_items
from app.transcript import clean


def _sentences():
    return [l.text for l in clean(SAMPLE.read_text())]


def test_lemmatize():
    assert lemmatize("jumping") == "jump"
    assert lemmatize("puddles") == "puddle"
    assert lemmatize("raining") == "rain"
    assert lemmatize("running") == "run"
    assert lemmatize("morning") == "morning"
    assert lemmatize("went") == "go"


def test_word_candidates_rank_visual_frequent_words_first():
    top = [c.text for c in word_candidates(_sentences())[:6]]
    for w in ("muddy", "jump", "puddle", "boots"):
        assert w in top
    assert "peppa" not in [c.text for c in word_candidates(_sentences())]  # 角色名排除


def test_phrase_candidates_merge_inflections():
    texts = [c.text for c in phrase_candidates(_sentences())]
    assert "jump up and down" in texts
    assert "jumping up and down" not in texts


def test_offline_extract_returns_ten_items_with_traceable_sentences():
    s = _sentences()
    result, mode = asyncio.run(extract("Peppa Pig", s, set(), 10))
    assert mode == "offline"
    assert len(result.selected) == 10
    assert 2 <= sum(1 for i in result.selected if i.type == "phrase") <= 3
    for it in result.selected:
        assert it.source_sentence in s


def test_mastered_words_are_demoted():
    s = _sentences()
    result, _ = asyncio.run(extract("Peppa Pig", s, {"muddy", "jump"}, 6))
    assert "muddy" not in [i.text for i in result.selected]


def test_validate_items_fixes_sentence_and_drops_unseen():
    s = _sentences()
    base = dict(type="noun", meaning_zh="", image_prompt="", emoji="⭐", visualizability=5, reason="")
    items = [
        ExtractedItem(text="boots", source_sentence="Not a real line.", **base),
        ExtractedItem(text="spaceship", source_sentence="", **base),
        ExtractedItem(text="boots", source_sentence="", **base),
    ]
    out = validate_items(items, s)
    assert [i.text for i in out] == ["boots"]
    assert out[0].source_sentence == find_sentence("boots", s)
