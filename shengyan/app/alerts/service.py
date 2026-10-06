"""预警判定与推送（技术文档第 5 节第 4 步）。"""
import logging
import time
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import utcnow
from ..models import Alert, AlertDelivery, Hit
from ..settings_store import get_notify
from .channels import AlertMessage, ChannelError, send_email, send_feishu, send_wecom

log = logging.getLogger(__name__)

DEDUP_WINDOW = timedelta(hours=6)
RETRY_DELAYS = (1, 2)


def _fmt(n: int) -> str:
    return f"{n / 10000:.1f}万" if n >= 10000 else str(n)


def in_quiet_hours(notify: dict, tz: str, now_utc: datetime | None = None) -> bool:
    if not notify.get("quiet_enabled"):
        return False
    now = (now_utc or utcnow()).replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(tz)).time()
    try:
        start = dtime.fromisoformat(notify["quiet_start"])
        end = dtime.fromisoformat(notify["quiet_end"])
    except (KeyError, ValueError):
        return False
    if start == end:
        return False
    return start <= now < end if start < end else (now >= start or now < end)


class Notifier:
    def __init__(self, settings: Settings, client: httpx.Client | None = None, sleep=time.sleep):
        self.settings = settings
        self.client = client or httpx.Client(timeout=10)
        self.sleep = sleep

    def enabled_channels(self, notify: dict) -> list[str]:
        out = []
        if notify.get("wecom_enabled") and notify.get("wecom_webhook"):
            out.append("wecom")
        if notify.get("feishu_enabled") and notify.get("feishu_webhook"):
            out.append("feishu")
        if notify.get("email_enabled") and notify.get("email_to"):
            out.append("email")
        return out

    def send(self, channel: str, notify: dict, msg: AlertMessage) -> None:
        if channel == "wecom":
            send_wecom(self.client, notify["wecom_webhook"], msg)
        elif channel == "feishu":
            send_feishu(self.client, notify["feishu_webhook"], msg)
        elif channel == "email":
            send_email(self.settings, notify["email_to"], msg)
        else:
            raise ChannelError(f"未知渠道 {channel}")

    def send_with_retry(self, channel: str, notify: dict, msg: AlertMessage) -> tuple[bool, int, str | None]:
        error = None
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                self.send(channel, notify, msg)
                return True, attempt + 1, None
            except (ChannelError, httpx.HTTPError, ValueError) as e:
                error = str(e) or type(e).__name__
                if attempt < len(RETRY_DELAYS):
                    self.sleep(RETRY_DELAYS[attempt])
        log.warning("预警推送失败 channel=%s：%s", channel, error)
        return False, len(RETRY_DELAYS) + 1, error


def build_message(hit: Hit, base_url: str) -> AlertMessage:
    p = hit.post
    excerpt = (p.title or p.content or "")[:40]
    return AlertMessage(
        title=f"【负面预警】{hit.group.name} · 小红书",
        lines=[f"作者：{p.author_name or '未知'}", f"摘录：{excerpt}",
               f"互动：赞 {_fmt(p.like_cnt)} · 评 {_fmt(p.comment_cnt)} · 藏 {_fmt(p.collect_cnt)}",
               f"命中词：{hit.matched_word}"],
        links=[("查看原文", p.url), ("在系统中处理", f"{base_url}/#hit-{hit.id}")],
    )


def deliver(db: Session, notifier: Notifier, alerts: list[Alert], msg: AlertMessage, notify: dict) -> list[AlertDelivery]:
    deliveries = []
    for channel in notifier.enabled_channels(notify):
        ok, attempts, error = notifier.send_with_retry(channel, notify, msg)
        for a in alerts:
            d = AlertDelivery(alert_id=a.id, channel=channel, status="ok" if ok else "failed",
                              attempts=attempts, sent_at=utcnow() if ok else None, error=error)
            db.add(d)
            deliveries.append(d)
    db.flush()
    return deliveries


def maybe_alert(db: Session, hit: Hit, notifier: Notifier, base_url: str) -> Alert | None:
    """负面且置信度达标、不是回溯数据、相似组 6 小时内没推过 → 生成预警。"""
    notify = get_notify(db)
    if hit.is_backfill or hit.is_irrelevant or hit.effective_sentiment != "neg":
        return None
    if hit.sentiment_manual is None and hit.confidence < float(notify.get("neg_threshold", 0.6)):
        return None
    group_key = hit.post.similar_group_id or hit.post.id
    recent = db.scalar(select(Alert.id).join(Hit).where(
        Alert.similar_group_id == group_key, Hit.group_id == hit.group_id,
        Alert.created_at >= utcnow() - DEDUP_WINDOW).limit(1))
    if recent:
        return None
    quiet = in_quiet_hours(notify, notifier.settings.timezone)
    alert = Alert(hit_id=hit.id, similar_group_id=group_key, status="queued" if quiet else "sent")
    db.add(alert)
    db.flush()
    if not quiet:
        deliver(db, notifier, [alert], build_message(hit, base_url), notify)
    return alert


def flush_quiet_queue(db: Session, notifier: Notifier, base_url: str) -> int:
    """免打扰结束后，把排队的预警合并成一条摘要推送。"""
    notify = get_notify(db)
    if in_quiet_hours(notify, notifier.settings.timezone):
        return 0
    queued = list(db.scalars(select(Alert).where(Alert.status == "queued").order_by(Alert.id)))
    if not queued:
        return 0
    lines = []
    for a in queued[:10]:
        p = a.hit.post
        lines.append(f"{a.hit.group.name}｜{p.author_name}：{(p.title or p.content)[:30]}")
    if len(queued) > 10:
        lines.append(f"……另有 {len(queued) - 10} 条")
    msg = AlertMessage(title=f"【免打扰期间的负面预警】共 {len(queued)} 条", lines=lines,
                       links=[("在系统中查看", f"{base_url}/")])
    deliver(db, notifier, queued, msg, notify)
    for a in queued:
        a.status = "sent"
    db.flush()
    return len(queued)


def send_test(db: Session, notifier: Notifier) -> dict[str, str]:
    notify = get_notify(db)
    msg = AlertMessage(title="【测试预警】声眼舆情", lines=["这是一条测试消息，收到说明推送渠道配置正确。"])
    result = {}
    channels = notifier.enabled_channels(notify)
    if not channels:
        return {"_": "没有已启用的推送渠道"}
    for ch in channels:
        ok, _, err = notifier.send_with_retry(ch, notify, msg)
        result[ch] = "ok" if ok else (err or "failed")
    return result
