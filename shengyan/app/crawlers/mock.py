"""演示用数据源：没有 TikHub Token 时自动启用，生成像小红书笔记的示例内容。

每个时间桶（采集间隔）产生几条新笔记；第 p 页返回更早一个桶的笔记，
所以下一轮采集会在第 1 页后碰到已入库的笔记，从而触发“遇到旧笔记停止翻页”。
"""
import hashlib
import random
from datetime import datetime, timedelta, timezone

from .base import NoteData, SearchPage

AUTHORS = ["早八续命研究所", "momo在上海", "探店的胖虎", "奶茶咖啡不分家", "城市夜跑的阿凯",
           "豆子实验室", "周末去哪儿", "打工人小陈", "精致穷鬼日记", "一只橘子"]
TEMPLATES = [
    ("neg", "避雷！{kw}这次真的踩雷了", "买了{kw}，拆开就有股怪味，联系客服也没给说法，太失望了。"),
    ("neg", "{kw}售后太差了", "{kw}出了问题申请退款，客服一直踢皮球，三天了还没处理。"),
    ("neg", "说说{kw}的排队问题", "工作日早上去{kw}排了二十分钟，出杯很慢，体验很差。"),
    ("pos", "{kw}真的回购无数次", "{kw}口感很稳定，包装也好看，已经推荐给同事了。"),
    ("pos", "打卡{kw}，太出片了", "环境很好，店员推荐的{kw}也很好喝，强烈推荐！"),
    ("neu", "{kw}和同类产品对比记录", "最近试了{kw}和另外几家，记录一下差异，大家按需选择。"),
    ("neu", "今天的早餐搭配", "今天搭配的是{kw}，中规中矩，下次试试别的。"),
]


class MockXhsCrawler:
    platform = "xhs"

    def __init__(self, interval_min: int = 10, per_bucket: int = 3, max_pages: int = 6):
        self.interval = timedelta(minutes=max(1, interval_min))
        self.per_bucket = per_bucket
        self.max_pages = max_pages

    def _bucket_start(self, now: datetime, offset: int) -> datetime:
        secs = self.interval.total_seconds()
        start = datetime.fromtimestamp((now.timestamp() // secs) * secs, tz=timezone.utc)
        return start - self.interval * offset

    def search(self, keyword: str, page: int = 1, search_id: str | None = None,
               time_filter: str = "一天内") -> SearchPage:
        now = datetime.now(timezone.utc)
        start = self._bucket_start(now, page - 1)
        kw_hash = hashlib.md5(keyword.encode()).hexdigest()[:8]
        notes = []
        for i in range(self.per_bucket):
            seed = f"{kw_hash}-{int(start.timestamp())}-{i}"
            rng = random.Random(seed)
            _, title, body = rng.choice(TEMPLATES)
            note_id = hashlib.md5(seed.encode()).hexdigest()[:24]
            # 发布时间落在时间桶内且不晚于现在（当前桶还没走完时压缩到已过去的部分）
            span = min(self.interval, now - start).total_seconds()
            published = start + timedelta(seconds=span * rng.random())
            likes = rng.choice([12, 86, 230, 640, 1832, 3120, 12400])
            notes.append(NoteData(
                platform_post_id=note_id,
                title=title.format(kw=keyword),
                content=body.format(kw=keyword),
                author_id=f"u{rng.randint(100000, 999999)}",
                author_name=rng.choice(AUTHORS),
                note_type=rng.choice(["normal", "video"]),
                published_at=published.replace(tzinfo=None),
                like_cnt=likes,
                comment_cnt=likes // rng.randint(4, 12),
                collect_cnt=likes // rng.randint(2, 6),
                share_cnt=likes // rng.randint(10, 40),
                url=f"https://www.xiaohongshu.com/explore/{note_id}",
                raw={"mock": True, "seed": seed},
            ))
        notes.sort(key=lambda n: n.published_at, reverse=True)
        return SearchPage(notes=notes, search_id=search_id or f"mock-{kw_hash}", has_more=page < self.max_pages)
