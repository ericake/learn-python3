import pytest

from app.transcript import TranscriptError, clean, validate

SRT = """1
00:00:01,000 --> 00:00:03,500
<i>NARRATOR: It is raining today.</i>

2
00:00:04,000 --> 00:00:06,000
PEPPA: I love jumping
in muddy puddles! [laughs]

3
00:00:07,000 --> 00:00:08,000
♪ La la la ♪
- Splash! Splash!
"""


def test_clean_srt_strips_timing_tags_and_annotations():
    lines = clean(SRT)
    texts = [l.text for l in lines]
    assert texts == ["It is raining today.", "I love jumping in muddy puddles!", "Splash!"]
    assert lines[0].speaker == "NARRATOR"
    assert lines[1].speaker == "PEPPA"


def test_clean_vtt_and_dedupes_consecutive_lines():
    vtt = "WEBVTT\n\n00:01.000 --> 00:02.000\nLook at me!\n\n00:02.000 --> 00:03.000\nLook at me!\nI can jump."
    assert [l.text for l in clean(vtt)] == ["Look at me!", "I can jump."]


def test_validate_rejects_short_and_non_english():
    with pytest.raises(TranscriptError):
        validate("Hi.", clean("Hi."))
    zh = "今天下雨了。佩奇想出去玩。她穿上了靴子。"
    with pytest.raises(TranscriptError):
        validate(zh, clean(zh.replace("。", "。\n")) or [])


def test_validate_rejects_too_long():
    text = "It is raining. " * 2000
    with pytest.raises(TranscriptError):
        validate(text, clean(text))
