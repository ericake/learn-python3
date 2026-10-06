"""情感判断（技术文档第 5 节第 3 步）。

- LlmSentimentClassifier：调用 DeepSeek（OpenAI 兼容的 /chat/completions），输出 JSON。
- RuleSentimentClassifier：没有配置 Key 时的本地兜底，按情感词打分，仅用于演示。
两者都实现 classify()，失败时返回 None，调用方把命中记录标为“待判断”。
"""
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from ..config import Settings

log = logging.getLogger(__name__)


@dataclass
class SentimentResult:
    sentiment: str  # neg / neu / pos
    confidence: float
    reason: str = ""


@dataclass
class Example:
    text: str
    sentiment: str


class SentimentClassifier(Protocol):
    def classify(self, group_name: str, matched_word: str, title: str, content: str,
                 examples: list[Example] | None = None) -> SentimentResult | None: ...


SYSTEM_PROMPT = """你是品牌舆情分析员。判断一条小红书笔记对“监测主体”的态度，而不是笔记整体情绪。
- neg：对监测主体有批评、投诉、避雷、质疑、负面体验；
- pos：对监测主体有推荐、好评、正面体验；
- neu：只是提及、客观对比、与主体态度无关。
只输出 JSON：{"sentiment": "neg|neu|pos", "confidence": 0到1之间的小数, "reason": "不超过30字的理由"}"""

LABELS = {"neg", "neu", "pos"}


def build_messages(group_name: str, matched_word: str, title: str, content: str,
                   examples: list[Example] | None = None) -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    if examples:
        shots = "\n".join(f"- 「{e.text[:80]}」→ {e.sentiment}" for e in examples[:10])
        msgs.append({"role": "system", "content": f"该客户人工确认过的判断示例：\n{shots}"})
    msgs.append({"role": "user", "content": (
        f"监测主体（关键词组）：{group_name}\n命中词：{matched_word}\n"
        f"标题：{title or '（无）'}\n正文：{(content or '')[:1500]}")})
    return msgs


def parse_result(text: str) -> SentimentResult | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    label = str(data.get("sentiment", "")).strip().lower()
    if label not in LABELS:
        return None
    try:
        conf = min(1.0, max(0.0, float(data.get("confidence", 0.5))))
    except (TypeError, ValueError):
        conf = 0.5
    return SentimentResult(label, conf, str(data.get("reason", ""))[:100])


class LlmSentimentClassifier:
    def __init__(self, settings: Settings, client: httpx.Client | None = None, sleep=time.sleep, retries: int = 2):
        self._settings = settings
        self._client = client or httpx.Client(base_url=settings.llm_base_url, timeout=settings.llm_timeout_s)
        self._sleep = sleep
        self._retries = retries

    def classify(self, group_name, matched_word, title, content, examples=None):
        body = {
            "model": self._settings.llm_model,
            "messages": build_messages(group_name, matched_word, title, content, examples),
            "temperature": 0,
            "max_tokens": 200,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self._settings.llm_api_key}"}
        for attempt in range(self._retries + 1):
            try:
                resp = self._client.post("/chat/completions", json=body, headers=headers)
                if resp.status_code == 200:
                    text = resp.json()["choices"][0]["message"]["content"]
                    result = parse_result(text)
                    if result:
                        return result
                    log.warning("情感模型输出无法解析：%s", (text or "")[:200])
                else:
                    log.warning("情感模型返回 %s：%s", resp.status_code, resp.text[:300])
                    if resp.status_code in (401, 403):
                        return None
            except (httpx.HTTPError, KeyError, ValueError) as e:
                log.warning("情感模型调用失败：%s", type(e).__name__)
            if attempt < self._retries:
                self._sleep(1 + attempt)
        return None


NEG_WORDS = ["避雷", "踩雷", "失望", "差评", "太差", "很差", "难喝", "难吃", "投诉", "退款", "变质", "怪味",
             "踢皮球", "坑", "不推荐", "后悔", "垃圾", "排队", "慢", "过敏", "智商税", "翻车", "恶心", "糟糕"]
POS_WORDS = ["推荐", "回购", "好喝", "好吃", "喜欢", "出片", "惊喜", "满意", "不错", "好评", "宝藏", "绝了", "顺滑"]


class RuleSentimentClassifier:
    def classify(self, group_name, matched_word, title, content, examples=None):
        text = f"{title}{content}"
        neg = sum(text.count(w) for w in NEG_WORDS)
        pos = sum(text.count(w) for w in POS_WORDS) - text.count("不推荐")  # “不推荐”不算正面
        if neg == pos == 0:
            return SentimentResult("neu", 0.6, "规则：未出现情感词")
        if neg > pos:
            return SentimentResult("neg", min(0.95, 0.6 + 0.1 * (neg - pos)), "规则：负面词更多")
        if pos > neg:
            return SentimentResult("pos", min(0.95, 0.6 + 0.1 * (pos - neg)), "规则：正面词更多")
        return SentimentResult("neu", 0.5, "规则：正负相当")


def make_classifier(settings: Settings) -> SentimentClassifier:
    if settings.effective_sentiment_mode == "llm":
        return LlmSentimentClassifier(settings)
    return RuleSentimentClassifier()
