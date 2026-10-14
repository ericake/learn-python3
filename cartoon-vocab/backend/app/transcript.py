"""台词清洗与分句（PRD F2）。

支持直接粘贴的台词、SRT、VTT：去掉序号、时间轴、HTML 标签、音效标注，
识别说话人前缀，把被字幕断开的句子拼回去，再按句切分。
"""

import re
from dataclasses import asdict, dataclass

MAX_CHARS = 20_000
MIN_SENTENCES = 3

_TIMESTAMP = re.compile(r"^\s*\d{1,2}:\d{2}(:\d{2})?[,.]\d{1,3}\s*-->\s*\d{1,2}:\d{2}(:\d{2})?[,.]\d{1,3}.*$")
_INDEX = re.compile(r"^\s*\d+\s*$")
_TAG = re.compile(r"<[^>]+>|\{\\[^}]*\}")
_ANNOTATION = re.compile(r"[♪♫][^♪♫]*[♪♫]|\[[^\]]*\]|\([^)]*\)|[♪♫]+")
_SPEAKER = re.compile(r"^\s*(?:-\s*)?([A-Z][A-Za-z0-9 .'&-]{0,30}?)\s*:\s+(?=\S)")
_SENTENCE_END = re.compile(r"[.!?…][\"'”’)]*$")
_SPLIT = re.compile(r"(?<=[.!?…])[\"'”’]*\s+(?=[\"'“‘]?[A-Z0-9])")


@dataclass
class Line:
    idx: int
    speaker: str | None
    text: str


class TranscriptError(ValueError):
    pass


def _strip_line(raw: str) -> str:
    line = _TAG.sub("", raw)
    line = _ANNOTATION.sub("", line)
    line = line.replace(" ", " ")
    line = re.sub(r"^\s*-\s+", "", line)  # 对话破折号
    return re.sub(r"\s+", " ", line).strip()


def clean(text: str) -> list[Line]:
    """清洗台词并按句切分，返回带说话人的句子列表。"""
    segments: list[list] = []  # [speaker, text]
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not raw.strip() or raw.strip().upper().startswith("WEBVTT"):
            continue
        if _TIMESTAMP.match(raw) or _INDEX.match(raw):
            continue
        raw = _TAG.sub("", raw)
        speaker = None
        m = _SPEAKER.match(raw)
        if m and len(m.group(1).split()) <= 3:
            speaker = m.group(1).strip()
            raw = raw[m.end():]
        line = _strip_line(raw)
        if not line or not re.search(r"[A-Za-z]", line):
            continue
        prev = segments[-1] if segments else None
        if speaker is None and prev is not None and not _SENTENCE_END.search(prev[1]):
            prev[1] = f"{prev[1]} {line}"  # 被字幕断开的半句
        else:
            # 没有说话人前缀的新句子，沿用上一句的说话人
            segments.append([speaker if speaker is not None else (prev[0] if prev else None), line])

    lines: list[Line] = []
    for speaker, seg in segments:
        for sent in _SPLIT.split(seg):
            sent = sent.strip()
            if not sent or not re.search(r"[A-Za-z]", sent):
                continue
            if lines and lines[-1].text.lower() == sent.lower():
                continue  # 连续重复行
            lines.append(Line(idx=len(lines), speaker=speaker, text=sent))
    return lines


def validate(raw: str, lines: list[Line]) -> None:
    if len(raw) > MAX_CHARS:
        raise TranscriptError(f"台词过长（{len(raw)} 字符），上限 {MAX_CHARS}")
    if len(lines) < MIN_SENTENCES:
        raise TranscriptError("台词内容过少，至少需要 3 句")
    body = " ".join(l.text for l in lines)
    letters = sum(c.isascii() and c.isalpha() for c in body)
    non_space = sum(not c.isspace() for c in body)
    if non_space and letters / non_space < 0.6:
        raise TranscriptError("台词似乎不是英文")


def to_json(lines: list[Line]) -> list[dict]:
    return [asdict(l) for l in lines]
