from app.lessons.builder import MAX_LESSON_SECONDS, LessonBuilder, LessonItem, sounds_similar


def item(i, text, type_="noun", sentence=True):
    return LessonItem(vocab_id=f"v{i}", text=text, type=type_, image=f"img{i}", audio_n=f"an{i}",
                      audio_s=f"as{i}", sentence_audio=f"sa{i}" if sentence else None)


ITEMS = [item(0, "puddle"), item(1, "boots"), item(2, "jump", "verb"), item(3, "rain", "verb"),
         item(4, "muddy", "adj"), item(5, "mud"), item(6, "bath"), item(7, "splash", "verb"),
         item(8, "jump up and down", "phrase"), item(9, "muddy puddle", "phrase")]


def _choice_steps(steps):
    return [s for s in steps if "options" in s]


def test_preview_structure():
    steps = LessonBuilder(ITEMS, seed=1).preview()
    types = [s["type"] for s in steps]
    assert types[0] == "intro" and types[-1] == "outro"
    assert types.count("Q1") == 10
    assert types.count("Q3") == 8  # 每个单词至少考一次四选一
    assert types.count("Q5") == 2
    for s in _choice_steps(steps):
        assert s["answer"] in s["options"]
        assert len(set(s["options"])) == len(s["options"])
    for s in steps:
        if s["type"] == "Q3":
            assert len(s["options"]) == 4
        if s["type"] == "Q2":
            assert len(s["options"]) == 2


def test_answer_never_three_times_in_same_position():
    for seed in range(30):
        steps = _choice_steps(LessonBuilder(ITEMS, seed=seed).preview())
        pos = [s["options"].index(s["answer"]) for s in steps]
        assert all(not (pos[i] == pos[i + 1] == pos[i + 2]) for i in range(len(pos) - 2))


def test_preview_avoids_similar_sounding_distractors():
    assert sounds_similar("cat", "cap")
    items = [item(0, "cat"), item(1, "cap"), item(2, "dog"), item(3, "sun"), item(4, "tree")]
    for seed in range(20):
        steps = LessonBuilder(items, seed=seed).preview()
        for s in _choice_steps(steps):
            if s["answer"] == "img0":
                assert "img1" not in s["options"]


def test_review_without_preview_adds_intro_cards_and_extras_capped():
    extras = [item(20 + i, f"old{i}") for i in range(5)]
    steps = LessonBuilder(ITEMS, seed=2).review(did_preview=False, extras=extras)
    types = [s["type"] for s in steps]
    assert "warmup" not in types and types.count("Q1") == 10
    q3_items = {s["item"] for s in steps if s["type"] == "Q3"}
    assert len(q3_items & {e.vocab_id for e in extras}) == 3
    assert "Q4" in types


def test_review_with_preview_uses_warmup_and_fits_time():
    steps = LessonBuilder(ITEMS, seed=3).review(did_preview=True)
    assert steps[1]["type"] == "warmup"
    assert LessonBuilder.estimate_seconds(steps) <= MAX_LESSON_SECONDS


def test_single_item_has_no_choice_questions():
    steps = LessonBuilder([item(0, "puddle")], seed=0).preview()
    assert not _choice_steps(steps)
