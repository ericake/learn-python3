"""settings 表里的业务配置：推送渠道、免打扰、预警阈值、采集状态。"""
from sqlalchemy.orm import Session

from .models import Setting

NOTIFY_DEFAULTS = {
    "wecom_enabled": False,
    "wecom_webhook": "",
    "feishu_enabled": False,
    "feishu_webhook": "",
    "email_enabled": False,
    "email_to": "",
    "quiet_enabled": False,
    "quiet_start": "23:00",
    "quiet_end": "08:00",
    "neg_threshold": 0.6,
}

CRAWLER_DEFAULTS = {"auth_failed": False, "auth_error": "", "paused_until": None}


def get_value(db: Session, key: str, defaults: dict) -> dict:
    row = db.get(Setting, key)
    return {**defaults, **(row.value if row else {})}


def save_value(db: Session, key: str, value: dict) -> None:
    row = db.get(Setting, key)
    if row:
        row.value = dict(value)
    else:
        db.add(Setting(key=key, value=dict(value)))
    db.flush()


def get_notify(db: Session) -> dict:
    return get_value(db, "notify", NOTIFY_DEFAULTS)


def save_notify(db: Session, value: dict) -> dict:
    merged = {**get_notify(db), **{k: v for k, v in value.items() if k in NOTIFY_DEFAULTS}}
    save_value(db, "notify", merged)
    return merged


def get_crawler_status(db: Session) -> dict:
    return get_value(db, "crawler", CRAWLER_DEFAULTS)


def save_crawler_status(db: Session, **changes) -> dict:
    merged = {**get_crawler_status(db), **changes}
    save_value(db, "crawler", merged)
    return merged
