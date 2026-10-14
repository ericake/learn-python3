"""数据模型，对应技术文档第 4 节（MVP 单家庭，暂不含家长账号表）。"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class EpisodeStatus:
    DRAFT = "draft"
    EXTRACTING = "extracting"
    REVIEWING = "reviewing"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class Child(Base):
    __tablename__ = "child"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    nickname: Mapped[str] = mapped_column(String(50), default="Kiddo")
    avatar: Mapped[str] = mapped_column(String(50), default="pig")
    accent_pref: Mapped[str] = mapped_column(String(10), default="en-GB")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Asset(Base):
    __tablename__ = "asset"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    kind: Mapped[str] = mapped_column(String(10))  # audio / image
    storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    mime: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(50))
    prompt: Mapped[str] = mapped_column(Text, default="")
    # 浏览器朗读兜底时要读的文本（provider=browser 时 storage_key 为空）
    speak_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="ready")  # pending/ready/failed/rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VocabItem(Base):
    """全局词条：同一个词在不同剧集中复用图片和单词音频。"""

    __tablename__ = "vocab_item"
    __table_args__ = (UniqueConstraint("lemma", "type", "accent"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    text: Mapped[str] = mapped_column(String(100))
    lemma: Mapped[str] = mapped_column(String(100), index=True)
    type: Mapped[str] = mapped_column(String(10))
    accent: Mapped[str] = mapped_column(String(10), default="en-GB")
    emoji: Mapped[str | None] = mapped_column(String(20), nullable=True)
    default_image_id: Mapped[str | None] = mapped_column(ForeignKey("asset.id"), nullable=True)
    audio_normal_id: Mapped[str | None] = mapped_column(ForeignKey("asset.id"), nullable=True)
    audio_slow_id: Mapped[str | None] = mapped_column(ForeignKey("asset.id"), nullable=True)


class Episode(Base):
    __tablename__ = "episode"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    child_id: Mapped[str] = mapped_column(ForeignKey("child.id"))
    show_name: Mapped[str] = mapped_column(String(100))
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    transcript_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_clean: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=EpisodeStatus.DRAFT)
    planned_date: Mapped[date] = mapped_column(Date, default=lambda: date.today())
    target_item_count: Mapped[int] = mapped_column(Integer, default=10)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 后台任务进度，如 {"stage": "assets", "done": 12, "total": 40}
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    items: Mapped[list["EpisodeItem"]] = relationship(
        back_populates="episode", cascade="all, delete-orphan", order_by="EpisodeItem.sort_order"
    )


class EpisodeItem(Base):
    __tablename__ = "episode_item"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episode.id", ondelete="CASCADE"))
    vocab_item_id: Mapped[str] = mapped_column(ForeignKey("vocab_item.id"))
    source_sentence: Mapped[str] = mapped_column(Text, default="")
    sentence_audio_id: Mapped[str | None] = mapped_column(ForeignKey("asset.id"), nullable=True)
    meaning_zh: Mapped[str] = mapped_column(String(200), default="")
    image_prompt: Mapped[str] = mapped_column(Text, default="")
    image_id: Mapped[str | None] = mapped_column(ForeignKey("asset.id"), nullable=True)
    image_regen_count: Mapped[int] = mapped_column(Integer, default=0)
    visualizability: Mapped[int] = mapped_column(Integer, default=3)
    reason: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    is_backup: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    asset_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    episode: Mapped[Episode] = relationship(back_populates="items")
    vocab: Mapped[VocabItem] = relationship()


class LearningSession(Base):
    __tablename__ = "session"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    child_id: Mapped[str] = mapped_column(ForeignKey("child.id"))
    episode_id: Mapped[str | None] = mapped_column(ForeignKey("episode.id", ondelete="SET NULL"), nullable=True)
    mode: Mapped[str] = mapped_column(String(10))  # preview / review / spaced
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Attempt(Base):
    __tablename__ = "attempt"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    client_attempt_id: Mapped[str] = mapped_column(String(64), unique=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("session.id", ondelete="CASCADE"))
    vocab_item_id: Mapped[str] = mapped_column(ForeignKey("vocab_item.id"))
    question_type: Mapped[str] = mapped_column(String(5))
    option_ids: Mapped[list] = mapped_column(JSON, default=list)
    chosen_id: Mapped[str] = mapped_column(String(64))
    is_correct: Mapped[bool] = mapped_column(Boolean)
    is_first_try: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Mastery(Base):
    __tablename__ = "mastery"
    child_id: Mapped[str] = mapped_column(ForeignKey("child.id"), primary_key=True)
    vocab_item_id: Mapped[str] = mapped_column(ForeignKey("vocab_item.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(10), default="new")  # new/learning/mastered
    correct_streak: Mapped[int] = mapped_column(Integer, default=0)
    streak_days: Mapped[list] = mapped_column(JSON, default=list)  # 连续答对发生的日期（ISO）
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    review_stage: Mapped[int] = mapped_column(Integer, default=0)  # 0→第1天 1→第3天 2→第7天 3→完成
    first_learned_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_due_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class StickerAward(Base):
    __tablename__ = "sticker_award"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    child_id: Mapped[str] = mapped_column(ForeignKey("child.id"))
    session_id: Mapped[str] = mapped_column(ForeignKey("session.id", ondelete="CASCADE"), unique=True)
    sticker_key: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CostLedger(Base):
    __tablename__ = "cost_ledger"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    episode_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider: Mapped[str] = mapped_column(String(50))
    operation: Mapped[str] = mapped_column(String(50))
    units: Mapped[float] = mapped_column(Float, default=0)
    unit: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
