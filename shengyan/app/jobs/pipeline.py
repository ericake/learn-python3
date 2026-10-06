"""采集 → 匹配 → 去重 → 情感 → 预警（技术文档第 4、5 节）。"""
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..alerts.service import Notifier, flush_quiet_queue, maybe_alert
from ..analysis.matcher import match_group
from ..analysis.sentiment import Example, SentimentClassifier, make_classifier
from ..analysis.simhash import is_similar, normalize, simhash
from ..config import Settings, get_settings
from ..crawlers.base import Crawler, CrawlerAuthError, CrawlerError, CrawlerRetryableError, NoteData
from ..crawlers.mock import MockXhsCrawler
from ..crawlers.xiaohongshu import TikHubXhsCrawler
from ..db import session_scope, utcnow
from ..models import CrawlState, Hit, KeywordGroup, Post
from ..settings_store import get_crawler_status, save_crawler_status

log = logging.getLogger(__name__)
PLATFORM = "xhs"
GLOBAL_PAUSE_AFTER = 5  # 连续 5 次 429 / 5xx → 全局暂停
GLOBAL_PAUSE = timedelta(minutes=5)


@dataclass
class Services:
    settings: Settings
    crawler: Crawler
    classifier: SentimentClassifier
    notifier: Notifier
    consecutive_failures: int = 0
    running: set = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)


_services: Services | None = None


def build_services(settings: Settings | None = None) -> Services:
    settings = settings or get_settings()
    if settings.effective_crawler_mode == "tikhub":
        crawler: Crawler = TikHubXhsCrawler(settings)
    else:
        crawler = MockXhsCrawler(interval_min=settings.crawl_interval_min)
    return Services(settings=settings, crawler=crawler, classifier=make_classifier(settings),
                    notifier=Notifier(settings))


def get_services() -> Services:
    global _services
    if _services is None:
        _services = build_services()
    return _services


def set_services(services: Services | None) -> None:
    global _services
    _services = services


# ---------- 单条笔记处理 ----------

def _save_post(db: Session, note: NoteData) -> Post:
    now = utcnow()
    post = Post(platform=PLATFORM, platform_post_id=note.platform_post_id, url=note.url,
                title=note.title, content=note.content, author_id=note.author_id,
                author_name=note.author_name, note_type=note.note_type,
                published_at=note.published_at or now, published_at_estimated=note.published_at is None,
                like_cnt=note.like_cnt, comment_cnt=note.comment_cnt, collect_cnt=note.collect_cnt,
                share_cnt=note.share_cnt, simhash=simhash(note.title, note.content), raw=note.raw,
                first_seen_at=now)
    db.add(post)
    db.flush()
    since = now - timedelta(days=7)
    text = normalize(post.title, post.content)
    candidates = db.execute(select(Post.id, Post.simhash, Post.similar_group_id, Post.title, Post.content).where(
        Post.platform == PLATFORM, Post.id != post.id, Post.first_seen_at >= since)).all()
    for cid, ch, cgroup, ctitle, ccontent in candidates:
        if is_similar(post.simhash, text, ch, normalize(ctitle, ccontent)):
            post.similar_group_id = cgroup or cid
            break
    else:
        post.similar_group_id = post.id
    return post


def _examples(db: Session) -> list[Example]:
    rows = db.scalars(select(Hit).where(Hit.sentiment_manual.is_not(None)).order_by(Hit.id.desc()).limit(10))
    return [Example(text=(h.post.title + h.post.content), sentiment=h.sentiment_manual) for h in rows]


def classify_hit(db: Session, hit: Hit, services: Services) -> None:
    result = services.classifier.classify(hit.group.name, hit.matched_word, hit.post.title,
                                          hit.post.content, _examples(db))
    if result:
        hit.sentiment, hit.confidence, hit.sentiment_reason = result.sentiment, result.confidence, result.reason
    db.flush()


def match_post(db: Session, post: Post, services: Services, backfill: bool,
               groups: list[KeywordGroup] | None = None) -> list[Hit]:
    groups = groups if groups is not None else list(db.scalars(select(KeywordGroup).where(KeywordGroup.enabled)))
    hits = []
    for g in groups:
        if PLATFORM not in (g.platforms or []):
            continue
        word = match_group(post.title, post.content, g.words, g.exclude_words)
        if not word:
            continue
        if db.scalar(select(Hit.id).where(Hit.post_id == post.id, Hit.group_id == g.id)):
            continue
        hit = Hit(post_id=post.id, group_id=g.id, matched_word=word, is_backfill=backfill)
        db.add(hit)
        db.flush()
        db.refresh(hit)
        classify_hit(db, hit, services)
        maybe_alert(db, hit, services.notifier, services.settings.public_base_url)
        hits.append(hit)
    return hits


# ---------- 采集一个监测词 ----------

@dataclass
class CrawlResult:
    keyword: str
    pages: int = 0
    requests: int = 0
    new_posts: int = 0
    new_hits: int = 0
    error: str | None = None


def crawl_keyword(keyword: str, backfill: bool = False, services: Services | None = None) -> CrawlResult:
    services = services or get_services()
    s = services.settings
    res = CrawlResult(keyword)
    with services.lock:
        if keyword in services.running:
            res.error = "该监测词正在采集中"
            return res
        services.running.add(keyword)
    try:
        with session_scope() as db:
            state = db.scalar(select(CrawlState).where(CrawlState.platform == PLATFORM, CrawlState.keyword == keyword))
            if not state:
                state = CrawlState(platform=PLATFORM, keyword=keyword)
                db.add(state)
                db.flush()
            state.last_run_at = utcnow()
            last_success = state.last_success_at
        max_pages = s.backfill_max_pages if backfill else s.crawl_max_pages
        time_filter = "一周内" if backfill else "一天内"
        cutoff = utcnow() - timedelta(days=s.backfill_days) if backfill else None
        search_id = None
        for page in range(1, max_pages + 1):
            result = services.crawler.search(keyword, page=page, search_id=search_id, time_filter=time_filter)
            res.pages += 1
            res.requests += result.request_count
            search_id = result.search_id or search_id
            seen_existing = False
            with session_scope() as db:
                for note in result.notes:
                    existing = db.scalar(select(Post).where(Post.platform == PLATFORM,
                                                            Post.platform_post_id == note.platform_post_id))
                    if existing:
                        seen_existing = True
                        existing.like_cnt, existing.comment_cnt = note.like_cnt, note.comment_cnt
                        existing.collect_cnt, existing.share_cnt = note.collect_cnt, note.share_cnt
                        continue
                    if cutoff and note.published_at and note.published_at < cutoff:
                        continue
                    try:
                        with db.begin_nested():
                            post = _save_post(db, note)
                    except IntegrityError:  # 另一个监测词的任务刚刚写入了同一篇
                        seen_existing = True
                        continue
                    res.new_posts += 1
                    res.new_hits += len(match_post(db, post, services, backfill))
            earliest = min((n.published_at for n in result.notes if n.published_at), default=None)
            if not backfill and seen_existing:
                break
            if not backfill and last_success and earliest and earliest < last_success - timedelta(hours=1):
                break
            if backfill and earliest and earliest < cutoff:
                break
            if not result.has_more or not result.notes:
                break
        services.consecutive_failures = 0
        with session_scope() as db:
            state = db.scalar(select(CrawlState).where(CrawlState.platform == PLATFORM, CrawlState.keyword == keyword))
            state.last_success_at = utcnow()
            state.last_error = None
            state.last_new_count = res.new_posts
            state.last_request_count = res.requests
            if backfill:
                state.backfill_done = True
    except CrawlerAuthError as e:
        res.error = str(e)
        log.error("TikHub 授权失效，停止全部采集：%s", e)
        with session_scope() as db:
            save_crawler_status(db, auth_failed=True, auth_error=str(e))
    except (CrawlerRetryableError, CrawlerError) as e:
        res.error = str(e)
        if isinstance(e, CrawlerRetryableError):
            services.consecutive_failures += 1
            if services.consecutive_failures >= GLOBAL_PAUSE_AFTER:
                with session_scope() as db:
                    save_crawler_status(db, paused_until=(utcnow() + GLOBAL_PAUSE).isoformat())
                services.consecutive_failures = 0
        log.warning("采集「%s」失败：%s", keyword, e)
    finally:
        if res.error:
            with session_scope() as db:
                state = db.scalar(select(CrawlState).where(CrawlState.platform == PLATFORM,
                                                           CrawlState.keyword == keyword))
                if state:
                    state.last_error = res.error[:500]
        with services.lock:
            services.running.discard(keyword)
    log.info("采集「%s」%s：%s 页 %s 次请求，新增 %s 篇、%s 条命中%s", keyword, "回溯" if backfill else "增量",
             res.pages, res.requests, res.new_posts, res.new_hits, f"，错误：{res.error}" if res.error else "")
    return res


def rematch_group(group_id: int, services: Services | None = None) -> int:
    """新建 / 修改关键词组后，用近 BACKFILL_DAYS 天已入库的笔记补命中（标记为回溯，不预警）。"""
    services = services or get_services()
    since = utcnow() - timedelta(days=services.settings.backfill_days)
    count = 0
    with session_scope() as db:
        group = db.get(KeywordGroup, group_id)
        if not group or not group.enabled:
            return 0
        for post in db.scalars(select(Post).where(Post.platform == PLATFORM, Post.published_at >= since)):
            count += len(match_post(db, post, services, backfill=True, groups=[group]))
    return count


# ---------- 调度入口 ----------

def active_keywords(db: Session) -> list[str]:
    words: list[str] = []
    for g in db.scalars(select(KeywordGroup).where(KeywordGroup.enabled)):
        if PLATFORM in (g.platforms or []):
            words.extend(w for w in g.words if w not in words)
    return words


def crawler_blocked(db: Session) -> str | None:
    st = get_crawler_status(db)
    if st.get("auth_failed"):
        return "数据源授权失效"
    if st.get("paused_until") and datetime.fromisoformat(st["paused_until"]) > utcnow():
        return "请求过于频繁，暂停中"
    return None


def due_jobs(db: Session, settings: Settings) -> list[tuple[str, bool]]:
    """返回 [(监测词, 是否回溯)]：没回溯过的先回溯，其余按间隔到期。"""
    jobs = []
    interval = timedelta(minutes=settings.crawl_interval_min)
    for word in active_keywords(db):
        st = db.scalar(select(CrawlState).where(CrawlState.platform == PLATFORM, CrawlState.keyword == word))
        if not st or not st.backfill_done:
            jobs.append((word, True))
        elif not st.last_run_at or utcnow() - st.last_run_at >= interval:
            jobs.append((word, False))
    return jobs


def retry_pending_sentiment(services: Services, limit: int = 20) -> int:
    with session_scope() as db:
        pending = list(db.scalars(select(Hit).where(Hit.sentiment.is_(None),
                                                    Hit.created_at >= utcnow() - timedelta(days=1)).limit(limit)))
        for hit in pending:
            classify_hit(db, hit, services)
            maybe_alert(db, hit, services.notifier, services.settings.public_base_url)
        return len(pending)


def run_due(services: Services | None = None) -> list[CrawlResult]:
    services = services or get_services()
    with session_scope() as db:
        blocked = crawler_blocked(db)
        jobs = [] if blocked else due_jobs(db, services.settings)
    results = [crawl_keyword(word, backfill, services) for word, backfill in jobs]
    retry_pending_sentiment(services)
    with session_scope() as db:
        flush_quiet_queue(db, services.notifier, services.settings.public_base_url)
    return results


def cleanup(services: Services | None = None) -> int:
    services = services or get_services()
    cutoff = utcnow() - timedelta(days=services.settings.retention_days)
    with session_scope() as db:
        n = db.scalar(select(func.count(Post.id)).where(Post.first_seen_at < cutoff)) or 0
        old_ids = select(Post.id).where(Post.first_seen_at < cutoff)
        db.execute(delete(Hit).where(Hit.post_id.in_(old_ids)))
        db.execute(delete(Post).where(Post.first_seen_at < cutoff))
    return n
