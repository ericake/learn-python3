"""后端 API（技术文档第 7 节），前缀 /api/v1。

单租户本地部署，不需要登录；服务默认只监听 127.0.0.1。
"""
import io
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..alerts.channels import validate_webhook
from ..alerts.service import send_test
from ..config import get_settings
from ..db import get_db, utcnow
from ..jobs import pipeline, scheduler
from ..models import Alert, AlertDelivery, CrawlState, Hit, KeywordGroup, Post
from ..settings_store import get_crawler_status, get_notify, save_crawler_status, save_notify

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")
SENTIMENTS = {"neg", "neu", "pos"}


def iso(dt: datetime | None) -> str | None:
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def local_day_start_utc(days_ago: int = 0) -> datetime:
    tz = ZoneInfo(get_settings().timezone)
    now_local = datetime.now(tz)
    start = now_local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
    return start.astimezone(timezone.utc).replace(tzinfo=None)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, f"时间格式不正确：{value}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(get_settings().timezone))
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


# ---------- 概况与系统状态 ----------

def system_status(db: Session) -> dict:
    s = get_settings()
    last_success = db.scalar(select(func.max(CrawlState.last_success_at)))
    st = get_crawler_status(db)
    words = pipeline.active_keywords(db)
    delayed = bool(words) and (last_success is None or utcnow() - last_success > timedelta(minutes=30))
    if st.get("auth_failed"):
        state, message = "auth_failed", "数据源授权失效，请检查 TikHub Token"
    elif st.get("paused_until") and datetime.fromisoformat(st["paused_until"]) > utcnow():
        state, message = "paused", "数据源请求过于频繁，暂停 5 分钟"
    elif delayed and last_success is not None:
        state, message = "delayed", "数据延迟：超过 30 分钟没有成功采集"
    elif not words:
        state, message = "idle", "还没有启用的关键词组"
    elif last_success is None:
        state, message = "starting", "正在进行首次采集"
    else:
        state, message = "ok", "采集正常"
    return {"state": state, "message": message, "last_success_at": iso(last_success),
            "crawler_mode": s.effective_crawler_mode, "sentiment_mode": s.effective_sentiment_mode,
            "interval_min": s.crawl_interval_min, "keyword_count": len(words)}


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    start = local_day_start_utc()
    base = select(Hit).join(Post).where(Hit.is_irrelevant.is_(False), Post.published_at >= start)
    eff = func.coalesce(Hit.sentiment_manual, Hit.sentiment)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    neg = db.scalar(select(func.count()).select_from(base.where(eff == "neg").subquery()))
    neg_open = db.scalar(select(func.count()).select_from(base.where(eff == "neg", Hit.status == "open").subquery()))
    alerts = db.scalar(select(func.count(Alert.id)).where(Alert.created_at >= start))
    groups = db.scalar(select(func.count(KeywordGroup.id)).where(KeywordGroup.enabled))
    all_neg_open = db.scalar(select(func.count(Hit.id)).where(Hit.is_irrelevant.is_(False), eff == "neg",
                                                              Hit.status == "open"))
    return {"today_hits": total, "today_neg": neg, "today_neg_open": neg_open, "today_alerts": alerts,
            "enabled_groups": groups, "neg_open_total": all_neg_open, "system": system_status(db)}


@router.get("/system/status")
def get_system_status(db: Session = Depends(get_db)):
    return system_status(db)


@router.post("/system/crawler/resume")
def resume_crawler(db: Session = Depends(get_db)):
    save_crawler_status(db, auth_failed=False, auth_error="", paused_until=None)
    db.commit()
    scheduler.trigger_now()
    return system_status(db)


@router.post("/system/crawl-now")
def crawl_now():
    scheduler.trigger_now()
    return {"ok": True}


# ---------- 信息流 ----------

def hit_query(db: Session, group_id, sentiment, status, q, date_from, date_to):
    eff = func.coalesce(Hit.sentiment_manual, Hit.sentiment)
    stmt = select(Hit).join(Post).where(Hit.is_irrelevant.is_(False))
    if group_id:
        stmt = stmt.where(Hit.group_id == group_id)
    if sentiment == "pending":
        stmt = stmt.where(eff.is_(None))
    elif sentiment:
        stmt = stmt.where(eff == sentiment)
    if status in ("open", "done"):
        stmt = stmt.where(Hit.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Post.title.like(like), Post.content.like(like), Post.author_name.like(like)))
    if date_from:
        stmt = stmt.where(Post.published_at >= date_from)
    if date_to:
        stmt = stmt.where(Post.published_at < date_to)
    return stmt


def hit_out(h: Hit, similar: dict[int, int], alerts: dict[int, int]) -> dict:
    p = h.post
    return {
        "id": h.id, "platform": p.platform, "group": {"id": h.group.id, "name": h.group.name},
        "matched_word": h.matched_word, "sentiment": h.effective_sentiment, "sentiment_model": h.sentiment,
        "confidence": round(h.confidence, 2), "reason": h.sentiment_reason, "manual": h.sentiment_manual is not None,
        "status": h.status, "is_backfill": h.is_backfill, "created_at": iso(h.created_at),
        "alert_id": alerts.get(h.id), "similar_count": max(0, similar.get(p.similar_group_id or p.id, 1) - 1),
        "post": {"id": p.id, "url": p.url, "title": p.title, "content": p.content, "author_name": p.author_name,
                 "note_type": p.note_type, "published_at": iso(p.published_at),
                 "published_at_estimated": p.published_at_estimated, "like": p.like_cnt, "comment": p.comment_cnt,
                 "collect": p.collect_cnt, "share": p.share_cnt},
    }


def enrich(db: Session, hits: list[Hit]) -> list[dict]:
    gids = {h.post.similar_group_id for h in hits if h.post.similar_group_id}
    similar = dict(db.execute(select(Post.similar_group_id, func.count(Post.id))
                              .where(Post.similar_group_id.in_(gids)).group_by(Post.similar_group_id)).all()) if gids else {}
    alerts = dict(db.execute(select(Alert.hit_id, Alert.id).where(Alert.hit_id.in_([h.id for h in hits]))).all()) if hits else {}
    return [hit_out(h, similar, alerts) for h in hits]


@router.get("/hits")
def list_hits(group_id: int | None = None, sentiment: Literal["neg", "neu", "pos", "pending"] | None = None,
              status: Literal["open", "done", "all"] = "open", q: str | None = Query(None, max_length=50),
              date_from: str | None = Query(None, alias="from"), date_to: str | None = Query(None, alias="to"),
              cursor: int | None = None, limit: int = Query(20, ge=1, le=50),
              db: Session = Depends(get_db)):
    stmt = hit_query(db, group_id, sentiment, status, q, parse_dt(date_from), parse_dt(date_to))
    if cursor:
        stmt = stmt.where(Hit.id < cursor)
    rows = list(db.scalars(stmt.order_by(Hit.id.desc()).limit(limit + 1)).unique())
    next_cursor = rows[limit - 1].id if len(rows) > limit else None
    return {"items": enrich(db, rows[:limit]), "next_cursor": next_cursor}


@router.get("/hits/export")
def export_hits(group_id: int | None = None, sentiment: Literal["neg", "neu", "pos", "pending"] | None = None,
                status: Literal["open", "done", "all"] = "all", q: str | None = Query(None, max_length=50),
                date_from: str | None = Query(None, alias="from"), date_to: str | None = Query(None, alias="to"),
                db: Session = Depends(get_db)):
    stmt = hit_query(db, group_id, sentiment, status, q, parse_dt(date_from), parse_dt(date_to))
    rows = list(db.scalars(stmt.order_by(Hit.id.desc()).limit(10_000)).unique())
    tz = ZoneInfo(get_settings().timezone)
    label = {"neg": "负面", "neu": "中性", "pos": "正面", None: "待判断"}
    wb = Workbook()
    ws = wb.active
    ws.title = "舆情"
    ws.append(["发布时间", "关键词组", "命中词", "情感", "是否人工修正", "处理状态", "作者", "标题", "正文",
               "点赞", "评论", "收藏", "分享", "原文链接"])
    for h in rows:
        p = h.post
        ws.append([p.published_at.replace(tzinfo=timezone.utc).astimezone(tz).strftime("%Y-%m-%d %H:%M"),
                   h.group.name, h.matched_word, label.get(h.effective_sentiment, "待判断"),
                   "是" if h.sentiment_manual else "否", "已处理" if h.status == "done" else "待处理",
                   p.author_name, p.title, p.content, p.like_cnt, p.comment_cnt, p.collect_cnt, p.share_cnt, p.url])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    name = f"shengyan-{datetime.now(tz).strftime('%Y%m%d-%H%M')}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


class HitPatch(BaseModel):
    sentiment_manual: Literal["neg", "neu", "pos"] | None = None
    is_irrelevant: bool | None = None
    status: Literal["open", "done"] | None = None


@router.patch("/hits/{hit_id}")
def patch_hit(hit_id: int, body: HitPatch, db: Session = Depends(get_db)):
    hit = db.get(Hit, hit_id)
    if not hit:
        raise HTTPException(404, "这条内容不存在或已过期")
    data = body.model_dump(exclude_unset=True)
    if "sentiment_manual" in data:
        hit.sentiment_manual = data["sentiment_manual"]
    if data.get("is_irrelevant") is not None:
        hit.is_irrelevant = data["is_irrelevant"]
    if data.get("status"):
        hit.status = data["status"]
    db.commit()
    return enrich(db, [hit])[0]


# ---------- 预警 ----------

@router.get("/alerts/{alert_id}")
def get_alert(alert_id: int, db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "预警不存在")
    deliveries = db.scalars(select(AlertDelivery).where(AlertDelivery.alert_id == a.id))
    return {"id": a.id, "status": a.status, "feedback": a.feedback, "created_at": iso(a.created_at),
            "hit": enrich(db, [a.hit])[0],
            "deliveries": [{"channel": d.channel, "status": d.status, "attempts": d.attempts,
                            "sent_at": iso(d.sent_at), "error": d.error} for d in deliveries]}


class AlertPatch(BaseModel):
    feedback: Literal["valid", "invalid"] | None


@router.patch("/alerts/{alert_id}")
def patch_alert(alert_id: int, body: AlertPatch, db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "预警不存在")
    a.feedback = body.feedback
    db.commit()
    return {"id": a.id, "feedback": a.feedback}


# ---------- 关键词组 ----------

def _clean_words(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        v = re.sub(r"\s+", " ", str(v)).strip()
        if v and v not in out:
            out.append(v)
    return out


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    words: list[str]
    exclude_words: list[str] = []
    platforms: list[str] = ["xhs"]
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("请填写关键词组名称")
        return v

    @field_validator("words", "exclude_words")
    @classmethod
    def _words(cls, v):
        v = _clean_words(v)
        if any(len(w) > 30 for w in v):
            raise ValueError("每个词最多 30 个字")
        return v

    @field_validator("platforms")
    @classmethod
    def _platforms(cls, v):
        if not v:
            raise ValueError("至少选择一个平台")
        if set(v) - {"xhs"}:
            raise ValueError("V1 仅支持小红书")
        return list(dict.fromkeys(v))


class GroupPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=20)
    words: list[str] | None = None
    exclude_words: list[str] | None = None
    enabled: bool | None = None

    @field_validator("words", "exclude_words")
    @classmethod
    def _words(cls, v):
        return None if v is None else GroupIn._words(v)


def group_out(db: Session, g: KeywordGroup) -> dict:
    start = local_day_start_utc()
    today = db.scalar(select(func.count(Hit.id)).join(Post).where(Hit.group_id == g.id, Hit.is_irrelevant.is_(False),
                                                                  Post.published_at >= start))
    return {"id": g.id, "name": g.name, "words": g.words, "exclude_words": g.exclude_words, "platforms": g.platforms,
            "enabled": g.enabled, "today_hits": today, "created_at": iso(g.created_at)}


def _check_limits(words: list[str]):
    s = get_settings()
    if not words:
        raise HTTPException(400, "至少填写一个监测词")
    if len(words) > s.max_words_per_group:
        raise HTTPException(400, f"每组最多 {s.max_words_per_group} 个监测词")


@router.get("/keyword-groups")
def list_groups(db: Session = Depends(get_db)):
    s = get_settings()
    groups = db.scalars(select(KeywordGroup).order_by(KeywordGroup.id))
    return {"items": [group_out(db, g) for g in groups],
            "limits": {"max_groups": s.max_groups, "max_words": s.max_words_per_group}}


@router.post("/keyword-groups", status_code=201)
def create_group(body: GroupIn, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    s = get_settings()
    if db.scalar(select(func.count(KeywordGroup.id))) >= s.max_groups:
        raise HTTPException(400, f"最多 {s.max_groups} 个关键词组，删除一组后可新建")
    _check_limits(body.words)
    g = KeywordGroup(**body.model_dump())
    db.add(g)
    db.commit()
    tasks.add_task(pipeline.rematch_group, g.id)
    tasks.add_task(scheduler.trigger_now)
    return group_out(db, g)


@router.put("/keyword-groups/{group_id}")
def update_group(group_id: int, body: GroupPatch, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    g = db.get(KeywordGroup, group_id)
    if not g:
        raise HTTPException(404, "关键词组不存在")
    data = body.model_dump(exclude_unset=True)
    if "words" in data:
        _check_limits(data["words"])
    if "name" in data:
        data["name"] = data["name"].strip()
        if not data["name"]:
            raise HTTPException(400, "请填写关键词组名称")
    for k, v in data.items():
        setattr(g, k, v)
    db.commit()
    if g.enabled and ({"words", "exclude_words", "enabled"} & data.keys()):
        tasks.add_task(pipeline.rematch_group, g.id)
        tasks.add_task(scheduler.trigger_now)
    return group_out(db, g)


@router.delete("/keyword-groups/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db)):
    g = db.get(KeywordGroup, group_id)
    if not g:
        raise HTTPException(404, "关键词组不存在")
    db.delete(g)
    db.commit()
    return {"ok": True}


# ---------- 推送设置 ----------

class NotifyIn(BaseModel):
    wecom_enabled: bool | None = None
    wecom_webhook: str | None = Field(None, max_length=300)
    feishu_enabled: bool | None = None
    feishu_webhook: str | None = Field(None, max_length=300)
    email_enabled: bool | None = None
    email_to: str | None = Field(None, max_length=300)
    quiet_enabled: bool | None = None
    quiet_start: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_end: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    neg_threshold: float | None = Field(None, ge=0, le=1)


def notify_out(n: dict) -> dict:
    out = dict(n)
    out["email_configured"] = bool(get_settings().smtp_host)
    return out


@router.get("/settings/notify")
def get_notify_settings(db: Session = Depends(get_db)):
    return notify_out(get_notify(db))


@router.put("/settings/notify")
def put_notify_settings(body: NotifyIn, db: Session = Depends(get_db)):
    data = {k: (v.strip() if isinstance(v, str) else v) for k, v in body.model_dump(exclude_unset=True).items()
            if v is not None}
    for ch in ("wecom", "feishu"):
        err = validate_webhook(ch, data.get(f"{ch}_webhook", ""))
        if err:
            raise HTTPException(400, err)
    merged = {**get_notify(db), **data}
    for ch, key, label in (("wecom", "wecom_webhook", "企业微信机器人地址"), ("feishu", "feishu_webhook", "飞书机器人地址"),
                           ("email", "email_to", "收件邮箱")):
        if merged.get(f"{ch}_enabled") and not merged.get(key):
            raise HTTPException(400, f"请先填写{label}再启用")
    saved = save_notify(db, data)
    db.commit()
    return notify_out(saved)


@router.post("/settings/notify/test")
def test_notify(db: Session = Depends(get_db)):
    return {"result": send_test(db, pipeline.get_services().notifier)}

