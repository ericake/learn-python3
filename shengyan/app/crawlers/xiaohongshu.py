"""TikHub 小红书搜索笔记适配器（技术文档第 3 节）。

接口：GET {base}/api/v1/xiaohongshu/app_v2/search_notes
TikHub 的返回结构尚未用真实 Token 核对过，所以字段映射写成“按候选路径依次查找”，
并且每条笔记都保存原始 JSON（posts.raw），联调确认后可以收紧映射、重新解析。
"""
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import Settings
from .base import CrawlerAuthError, CrawlerError, CrawlerRetryableError, NoteData, SearchPage

log = logging.getLogger(__name__)

RETRY_DELAYS = (2, 4, 8)


class RateLimiter:
    """全局限流：同时最多 N 个请求，两次请求之间至少间隔 min_interval 秒。"""

    def __init__(self, concurrency: int, min_interval_s: float):
        self._sem = threading.Semaphore(max(1, concurrency))
        self._lock = threading.Lock()
        self._min_interval = min_interval_s
        self._last = 0.0

    def __enter__(self):
        self._sem.acquire()
        with self._lock:
            wait = self._last + self._min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
        return self

    def __exit__(self, *exc):
        self._sem.release()


# ---------- 字段映射 ----------

def _get(d: Any, *paths: str, default=None):
    """按 'a.b.c' 形式的候选路径取第一个非空值。"""
    for path in paths:
        cur = d
        for key in path.split("."):
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                cur = None
                break
        if cur not in (None, ""):
            return cur
    return default


def _find_key(obj: Any, key: str, depth: int = 0):
    """在嵌套结构里找第一个名为 key 的值（用于 search_id / has_more）。"""
    if depth > 5:
        return None
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = _find_key(v, key, depth + 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj[:3]:
            found = _find_key(v, key, depth + 1)
            if found is not None:
                return found
    return None


def _to_int(v) -> int:
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(",", "")
    try:
        if s.endswith("万") or s.lower().endswith("w"):
            return int(float(s[:-1]) * 10000)
        if s.endswith("千") or s.lower().endswith("k"):
            return int(float(s[:-1]) * 1000)
        return int(float(s))
    except ValueError:
        return 0


def _to_datetime(v) -> datetime | None:
    if v in (None, "", 0):
        return None
    try:
        ts = float(v)
        if ts > 1e12:  # 毫秒
            ts /= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        return None


def _find_item_list(payload: Any) -> list:
    """找出笔记列表：优先常见路径，否则找第一个“元素像笔记”的列表。"""
    for path in ("data.data.items", "data.items", "data.data.notes", "data.notes", "items", "notes"):
        lst = _get(payload, path)
        if isinstance(lst, list):
            return lst

    def looks_like_note(x):
        return isinstance(x, dict) and ("note" in x or "note_card" in x or ("id" in x and ("title" in x or "desc" in x)))

    stack = [payload]
    while stack:
        cur = stack.pop()
        if isinstance(cur, list) and cur and any(looks_like_note(x) for x in cur):
            return cur
        if isinstance(cur, dict):
            stack.extend(cur.values())
    return []


def map_note(item: dict) -> NoteData | None:
    """把 TikHub 返回的一条结果映射成内部字段。非笔记条目（广告、推荐词）返回 None。"""
    if not isinstance(item, dict):
        return None
    note = item.get("note") or item.get("note_card") or item
    if not isinstance(note, dict):
        return None
    note_id = _get(note, "id", "note_id", "noteId") or _get(item, "id", "note_id")
    if not note_id:
        return None
    note_id = str(note_id)
    xsec = _get(note, "xsec_token") or _get(item, "xsec_token")
    url = f"https://www.xiaohongshu.com/explore/{note_id}" + (f"?xsec_token={xsec}" if xsec else "")
    return NoteData(
        platform_post_id=note_id,
        title=str(_get(note, "title", "display_title", default="")),
        content=str(_get(note, "desc", "content", "abstract_show", default="")),
        author_id=str(_get(note, "user.userid", "user.user_id", "user.id", "author.id", default="")),
        author_name=str(_get(note, "user.nickname", "user.nick_name", "user.name", "author.nickname", default="")),
        note_type=str(_get(note, "type", "note_type", "model_type", default="")),
        published_at=_to_datetime(_get(note, "timestamp", "time", "publish_time", "create_time", "last_update_time")),
        like_cnt=_to_int(_get(note, "liked_count", "likes", "interact_info.liked_count", "like_count")),
        comment_cnt=_to_int(_get(note, "comments_count", "comment_count", "interact_info.comment_count")),
        collect_cnt=_to_int(_get(note, "collected_count", "collect_count", "interact_info.collected_count")),
        share_cnt=_to_int(_get(note, "shared_count", "share_count", "interact_info.share_count")),
        url=url,
        raw=item,
    )


def parse_search_response(payload: dict) -> SearchPage:
    notes = [n for n in (map_note(x) for x in _find_item_list(payload)) if n]
    search_id = _find_key(payload, "search_id") or _find_key(payload, "searchId")
    has_more = _find_key(payload, "has_more")
    return SearchPage(notes=notes, search_id=str(search_id) if search_id else None,
                      has_more=bool(has_more) if has_more is not None else bool(notes))


# ---------- 客户端 ----------

class TikHubXhsCrawler:
    platform = "xhs"

    def __init__(self, settings: Settings, client: httpx.Client | None = None, sleep=time.sleep):
        if not settings.tikhub_api_key:
            raise CrawlerError("未配置 TIKHUB_API_KEY")
        self._settings = settings
        self._client = client or httpx.Client(base_url=settings.tikhub_base_url, timeout=settings.tikhub_timeout_s)
        self._limiter = RateLimiter(settings.tikhub_concurrency, settings.tikhub_min_interval_ms / 1000)
        self._sleep = sleep

    def search(self, keyword: str, page: int = 1, search_id: str | None = None,
               time_filter: str = "一天内") -> SearchPage:
        params = {"keyword": keyword, "page": page, "sort_type": "time_descending",
                  "note_type": "不限", "time_filter": time_filter}
        if search_id:
            params["search_id"] = search_id
        headers = {"Authorization": f"Bearer {self._settings.tikhub_api_key}"}
        last_error = ""
        attempts = 0
        for attempt in range(len(RETRY_DELAYS) + 1):
            attempts += 1
            try:
                with self._limiter:
                    resp = self._client.get(self._settings.tikhub_search_path, params=params, headers=headers)
            except httpx.TransportError as e:
                last_error = f"网络错误：{type(e).__name__}"
            else:
                if resp.status_code in (401, 403):
                    raise CrawlerAuthError(f"TikHub 返回 {resp.status_code}，Token 可能已失效")
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = f"TikHub 返回 {resp.status_code}"
                elif resp.status_code != 200:
                    raise CrawlerError(f"TikHub 返回 {resp.status_code}：{resp.text[:2048]}")
                else:
                    payload = resp.json()
                    code = payload.get("code") if isinstance(payload, dict) else None
                    if code not in (None, 200, 0):
                        raise CrawlerError(f"TikHub 业务码 {code}：{str(payload)[:2048]}")
                    page_result = parse_search_response(payload)
                    page_result.request_count = attempts
                    return page_result
            if attempt < len(RETRY_DELAYS):
                log.warning("TikHub 请求失败（%s），%ss 后重试", last_error, RETRY_DELAYS[attempt])
                self._sleep(RETRY_DELAYS[attempt])
        raise CrawlerRetryableError(last_error)
