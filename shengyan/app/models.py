"""数据表，对应技术文档第 6 节。单租户，不设 tenant_id。"""
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(10), default="member")  # admin / member
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class KeywordGroup(Base):
    __tablename__ = "keyword_groups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    words: Mapped[list] = mapped_column(JSON, default=list)
    exclude_words: Mapped[list] = mapped_column(JSON, default=list)
    platforms: Mapped[list] = mapped_column(JSON, default=lambda: ["xhs"])
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class CrawlState(Base):
    __tablename__ = "crawl_states"
    __table_args__ = (UniqueConstraint("platform", "keyword"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(10))
    keyword: Mapped[str] = mapped_column(String(100))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    backfill_done: Mapped[bool] = mapped_column(Boolean, default=False)
    last_new_count: Mapped[int] = mapped_column(Integer, default=0)
    last_request_count: Mapped[int] = mapped_column(Integer, default=0)


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("platform", "platform_post_id"),
        Index("ix_posts_published_at", "published_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(10))
    platform_post_id: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(String(500), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    author_id: Mapped[str] = mapped_column(String(64), default="")
    author_name: Mapped[str] = mapped_column(String(100), default="")
    note_type: Mapped[str] = mapped_column(String(20), default="")
    published_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    published_at_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    like_cnt: Mapped[int] = mapped_column(Integer, default=0)
    comment_cnt: Mapped[int] = mapped_column(Integer, default=0)
    collect_cnt: Mapped[int] = mapped_column(Integer, default=0)
    share_cnt: Mapped[int] = mapped_column(Integer, default=0)
    simhash: Mapped[int] = mapped_column(BigInteger, default=0)
    similar_group_id: Mapped[int | None] = mapped_column(Integer, index=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Hit(Base):
    __tablename__ = "hits"
    __table_args__ = (
        UniqueConstraint("post_id", "group_id"),
        Index("ix_hits_group_created", "group_id", "created_at"),
        Index("ix_hits_sentiment_status", "sentiment", "status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(ForeignKey("keyword_groups.id", ondelete="CASCADE"))
    matched_word: Mapped[str] = mapped_column(String(100))
    sentiment: Mapped[str | None] = mapped_column(String(10))  # neg / neu / pos；None = 待判断
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    sentiment_reason: Mapped[str] = mapped_column(Text, default="")
    sentiment_manual: Mapped[str | None] = mapped_column(String(10))
    is_irrelevant: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open / done
    is_backfill: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    post: Mapped[Post] = relationship(lazy="joined")
    group: Mapped[KeywordGroup] = relationship(lazy="joined")

    @property
    def effective_sentiment(self) -> str | None:
        return self.sentiment_manual or self.sentiment


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hit_id: Mapped[int] = mapped_column(ForeignKey("hits.id", ondelete="CASCADE"), index=True)
    similar_group_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="sent")  # queued（免打扰）/ sent
    feedback: Mapped[str | None] = mapped_column(String(10))  # valid / invalid
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    hit: Mapped[Hit] = relationship(lazy="joined")


class AlertDelivery(Base):
    __tablename__ = "alert_deliveries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10))  # ok / failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(Text)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
