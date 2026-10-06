"""关键词二次校验（技术文档第 5 节第 1 步）。

TikHub 搜索是模糊匹配，这里要求正文真的包含监测词：
- 含空格的监测词（如“山岚 门店”）拆开后每一段都要出现；
- 命中任一排除词就丢弃。
"""


def _norm(text: str) -> str:
    return (text or "").lower()


def match_word(text: str, word: str) -> bool:
    parts = [p for p in _norm(word).split() if p]
    return bool(parts) and all(p in text for p in parts)


def match_group(title: str, content: str, words: list[str], exclude_words: list[str]) -> str | None:
    """返回命中的监测词；未命中或命中排除词时返回 None。"""
    text = _norm(f"{title}\n{content}")
    if any(match_word(text, ex) for ex in exclude_words or []):
        return None
    for w in words or []:
        if match_word(text, w):
            return w
    return None
