"""相似内容归并。

只用 SimHash 时，小红书这类短文本改一个字就会翻转十几位，误判太多。这里分两步：
1. SimHash 粗筛：汉明距离 ≤ PREFILTER_DISTANCE 的才进入下一步（存库，便于快速比较）；
2. 字符二元组 Jaccard 相似度 ≥ 0.85 视为同一相似组（约对应 PRD 中“相似度 ≥ 0.9”）。
"""
import hashlib
import re

BITS = 63  # 存进有符号 BIGINT，只用 63 位
MASK = (1 << BITS) - 1
PREFILTER_DISTANCE = 24
JACCARD_THRESHOLD = 0.85
_STRIP = re.compile(r"[\s\W_]+", re.UNICODE)


def normalize(title: str, content: str) -> str:
    return _STRIP.sub("", f"{title}{(content or '')[:200]}".lower())


def shingles(text: str) -> set[str]:
    if len(text) < 2:
        return {text} if text else set()
    return {text[i:i + 2] for i in range(len(text) - 1)}


def simhash(title: str, content: str) -> int:
    feats = shingles(normalize(title, content))
    if not feats:
        return 0
    v = [0] * BITS
    for f in feats:
        h = int.from_bytes(hashlib.md5(f.encode()).digest()[:8], "big") & MASK
        for i in range(BITS):
            v[i] += 1 if h >> i & 1 else -1
    out = 0
    for i in range(BITS):
        if v[i] > 0:
            out |= 1 << i
    return out


def distance(a: int, b: int) -> int:
    return bin((a ^ b) & MASK).count("1")


def jaccard(a: str, b: str) -> float:
    sa, sb = shingles(a), shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def is_similar(hash_a: int, text_a: str, hash_b: int, text_b: str) -> bool:
    if not hash_a or not hash_b or distance(hash_a, hash_b) > PREFILTER_DISTANCE:
        return False
    return jaccard(text_a, text_b) >= JACCARD_THRESHOLD
