"""推送渠道：企业微信群机器人、飞书群机器人、SMTP 邮件。"""
import smtplib
import ssl
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from email.utils import formataddr

import httpx

from ..config import Settings

WECOM_PREFIX = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"
FEISHU_PREFIXES = ("https://open.feishu.cn/open-apis/bot/", "https://open.larksuite.com/open-apis/bot/")


class ChannelError(Exception):
    pass


@dataclass
class AlertMessage:
    title: str
    lines: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)  # (文字, 链接)


def validate_webhook(channel: str, url: str) -> str | None:
    """只允许官方机器人地址，避免服务端被用来请求任意地址。返回错误信息或 None。"""
    if not url:
        return None
    if channel == "wecom" and not url.startswith(WECOM_PREFIX):
        return f"企业微信机器人地址应以 {WECOM_PREFIX} 开头"
    if channel == "feishu" and not url.startswith(FEISHU_PREFIXES):
        return "飞书机器人地址应以 https://open.feishu.cn/open-apis/bot/ 开头"
    return None


def send_wecom(client: httpx.Client, webhook: str, msg: AlertMessage) -> None:
    text = f"**{msg.title}**\n" + "\n".join(f"> {line}" for line in msg.lines)
    if msg.links:
        text += "\n" + " · ".join(f"[{t}]({u})" for t, u in msg.links)
    resp = client.post(webhook, json={"msgtype": "markdown", "markdown": {"content": text}})
    data = resp.json() if resp.status_code == 200 else {}
    if resp.status_code != 200 or data.get("errcode") != 0:
        raise ChannelError(f"企业微信返回 {resp.status_code} {data.get('errmsg', '')}".strip())


def send_feishu(client: httpx.Client, webhook: str, msg: AlertMessage) -> None:
    content = [[{"tag": "text", "text": line}] for line in msg.lines]
    if msg.links:
        content.append([{"tag": "a", "text": t + "  ", "href": u} for t, u in msg.links])
    body = {"msg_type": "post", "content": {"post": {"zh_cn": {"title": msg.title, "content": content}}}}
    resp = client.post(webhook, json=body)
    data = resp.json() if resp.status_code == 200 else {}
    code = data.get("code", data.get("StatusCode"))
    if resp.status_code != 200 or code != 0:
        raise ChannelError(f"飞书返回 {resp.status_code} {data.get('msg', '')}".strip())


def send_email(settings: Settings, to: str, msg: AlertMessage) -> None:
    if not settings.smtp_host:
        raise ChannelError("未配置 SMTP_HOST")
    body = "\n".join(msg.lines + [f"{t}：{u}" for t, u in msg.links])
    mime = MIMEText(body, "plain", "utf-8")
    mime["Subject"] = msg.title
    mime["From"] = formataddr(("声眼舆情", settings.smtp_from or settings.smtp_user))
    mime["To"] = to
    recipients = [x.strip() for x in to.replace("，", ",").split(",") if x.strip()]
    try:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ssl.create_default_context(), timeout=15) as s:
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.sendmail(settings.smtp_from or settings.smtp_user, recipients, mime.as_string())
    except (smtplib.SMTPException, OSError) as e:
        raise ChannelError(f"邮件发送失败：{type(e).__name__}") from e
