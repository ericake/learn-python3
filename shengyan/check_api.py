"""联调检查：用 .env 里的 Key 真实请求一次 TikHub 和 DeepSeek，确认能抓到数据、字段映射正确。

用法（在 shengyan 目录）：
    python check_api.py            # 默认搜索“全嘻嘻”
    python check_api.py 其他关键词

TikHub 的原始响应会保存到 tikhub_sample.json（已加入 .gitignore），字段对不上时把它发给开发者。
"""
import json
import os
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit(f"需要 Python 3.10 或更高版本，当前是 {sys.version.split()[0]}")

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from app.analysis.matcher import match_group  # noqa: E402
from app.analysis.sentiment import LlmSentimentClassifier  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.crawlers.base import CrawlerAuthError, CrawlerError  # noqa: E402
from app.crawlers.xiaohongshu import TikHubXhsCrawler, parse_search_response  # noqa: E402

SAMPLE_FILE = ROOT / "tikhub_sample.json"


def check_tikhub(keyword: str):
    s = get_settings()
    print(f"== TikHub：搜索小红书「{keyword}」==")
    if not s.tikhub_api_key:
        print("[失败] .env 里没有 TIKHUB_API_KEY，无法抓取真实数据。")
        return None
    crawler = TikHubXhsCrawler(s)
    try:
        payload, _ = crawler.fetch_raw(keyword, page=1, time_filter="一周内")
    except CrawlerAuthError as e:
        print(f"[失败] {e}。请确认 Token 正确、未过期，且账户有余额。")
        return None
    except CrawlerError as e:
        print(f"[失败] 请求失败：{e}")
        return None
    SAMPLE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    page = parse_search_response(payload)
    print(f"[成功] 原始响应已保存到 {SAMPLE_FILE.name}")
    print(f"  解析出 {len(page.notes)} 篇笔记；search_id={page.search_id}；has_more={page.has_more}")
    if not page.notes:
        print("[失败] 没有解析出笔记：可能这个词近一周没有内容，也可能返回结构与映射不一致，请把 tikhub_sample.json 发给开发者。")
        return None
    strict = 0
    for i, n in enumerate(page.notes):
        hit = match_group(n.title, n.content, [keyword], [])
        strict += bool(hit)
        if i < 8:
            when = n.published_at.strftime("%Y-%m-%d %H:%M UTC") if n.published_at else "（无发布时间）"
            text = (n.title or n.content or "（无标题和正文）").replace("\n", " ")[:40]
            print(f"  {i + 1}. [{'命中' if hit else '未含关键词'}] {text}")
            print(f"     作者：{n.author_name or '（空）'}  时间：{when}  赞 {n.like_cnt} 评 {n.comment_cnt} 藏 {n.collect_cnt}")
    print(f"  其中 {strict}/{len(page.notes)} 篇的标题或正文包含「{keyword}」，系统只收录这些（其余视为搜索误召回）。")
    for field, label in (("author_name", "作者"), ("published_at", "发布时间"), ("like_cnt", "点赞数")):
        if not any(getattr(n, field) for n in page.notes):
            print(f"  [注意] 所有笔记的「{label}」都是空的，字段映射可能需要调整，请把 tikhub_sample.json 发给开发者。")
    return page.notes[0]


def check_deepseek(note):
    s = get_settings()
    print("\n== DeepSeek：情感判断 ==")
    if not s.llm_api_key:
        print("[失败] .env 里没有 LLM_API_KEY，系统会用本地规则判断情感（准确度有限）。")
        return
    title = note.title if note else "全嘻嘻这次的新品太让人失望了"
    content = note.content if note else "包装破损，客服也不回复，不会再买了。"
    r = LlmSentimentClassifier(s).classify("全嘻嘻", "全嘻嘻", title, content)
    if r:
        label = {"neg": "负面", "neu": "中性", "pos": "正面"}[r.sentiment]
        print(f"[成功] 第一篇判断为{label}，置信度 {r.confidence:.2f}，理由：{r.reason}")
    else:
        print("[失败] 调用失败，请检查 LLM_API_KEY 是否正确、账户是否有余额（详细原因见上方日志）。")


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.WARNING, format="  日志：%(message)s")
    kw = sys.argv[1] if len(sys.argv) > 1 else "全嘻嘻"
    first = check_tikhub(kw)
    check_deepseek(first)
