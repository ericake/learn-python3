from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class NoteData:
    platform_post_id: str
    title: str = ""
    content: str = ""
    author_id: str = ""
    author_name: str = ""
    note_type: str = ""
    published_at: datetime | None = None  # None 表示接口没给，入库时用首次采集时间
    like_cnt: int = 0
    comment_cnt: int = 0
    collect_cnt: int = 0
    share_cnt: int = 0
    url: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class SearchPage:
    notes: list[NoteData]
    search_id: str | None = None
    has_more: bool = True
    request_count: int = 1


class CrawlerError(Exception):
    pass


class CrawlerAuthError(CrawlerError):
    """401 / 403：Token 失效，需停止全部采集。"""


class CrawlerRetryableError(CrawlerError):
    """429 / 5xx / 超时，重试后仍失败。"""


class Crawler(Protocol):
    platform: str

    def search(self, keyword: str, page: int = 1, search_id: str | None = None,
               time_filter: str = "一天内") -> SearchPage: ...
