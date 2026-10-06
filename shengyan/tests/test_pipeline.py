import json
from datetime import timedelta

from sqlalchemy import func, select

from app.crawlers.base import NoteData
from app.db import session_scope, utcnow
from app.jobs import pipeline
from app.models import Alert, AlertDelivery, CrawlState, Hit, KeywordGroup, Post
from app.settings_store import get_crawler_status, save_notify


def note(i, title, content, minutes_ago=5):
    return NoteData(platform_post_id=f"n{i}", title=title, content=content, author_name=f"作者{i}",
                    published_at=utcnow() - timedelta(minutes=minutes_ago), like_cnt=100 + i,
                    url=f"https://www.xiaohongshu.com/explore/n{i}")


def setup_group(words=("冷萃挂耳",), exclude=()):
    with session_scope() as db:
        g = KeywordGroup(name="产品词", words=list(words), exclude_words=list(exclude), platforms=["xhs"])
        db.add(g)
        db.flush()
        save_notify(db, {"wecom_enabled": True, "wecom_webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=x"})
        return g.id


def mark_backfilled(word):
    with session_scope() as db:
        db.add(CrawlState(platform="xhs", keyword=word, backfill_done=True,
                          last_run_at=utcnow() - timedelta(hours=1), last_success_at=utcnow() - timedelta(hours=1)))


def count(model, *where):
    with session_scope() as db:
        return db.scalar(select(func.count()).select_from(model).where(*where))


def test_incremental_crawl_creates_hits_and_alerts(env):
    setup_group(exclude=["教程"])
    mark_backfilled("冷萃挂耳")
    env.crawler.pages["冷萃挂耳"] = [[
        note(1, "避雷！冷萃挂耳有怪味", "太失望了"),
        note(2, "冷萃挂耳回购", "强烈推荐"),
        note(3, "自制冷萃挂耳教程", "很简单"),       # 排除词
        note(4, "今天的咖啡", "没提到监测词"),        # 模糊召回，二次校验丢弃
    ]]
    res = pipeline.run_due(env.services)
    assert res[0].new_posts == 4 and res[0].new_hits == 2
    with session_scope() as db:
        hits = {h.post.platform_post_id: h for h in db.scalars(select(Hit))}
        assert hits["n1"].sentiment == "neg" and hits["n2"].sentiment == "pos"
        assert db.scalar(select(func.count(Alert.id))) == 1
        assert db.scalar(select(AlertDelivery.status)) == "ok"
    body = json.loads(env.hooks.requests[0].content)
    assert body["msgtype"] == "markdown" and "负面预警" in body["markdown"]["content"]


def test_stops_paging_on_existing_post(env):
    setup_group()
    mark_backfilled("冷萃挂耳")
    env.crawler.pages["冷萃挂耳"] = [[note(1, "冷萃挂耳", "a")], [note(2, "冷萃挂耳", "b")], [note(3, "冷萃挂耳", "c")]]
    pipeline.crawl_keyword("冷萃挂耳", services=env.services)
    assert [c[1] for c in env.crawler.calls] == [1, 2, 3]
    env.crawler.calls.clear()
    env.crawler.pages["冷萃挂耳"] = [[note(9, "冷萃挂耳 新", "x"), note(1, "冷萃挂耳", "a")], [note(2, "冷萃挂耳", "b")]]
    res = pipeline.crawl_keyword("冷萃挂耳", services=env.services)
    assert [c[1] for c in env.crawler.calls] == [1] and res.new_posts == 1


def test_backfill_runs_first_and_does_not_alert(env):
    setup_group()
    env.crawler.pages["冷萃挂耳"] = [[note(1, "避雷冷萃挂耳", "失望"), note(2, "冷萃挂耳太旧", "失望", minutes_ago=60 * 24 * 5)]]
    pipeline.run_due(env.services)
    assert env.crawler.calls[0][2] == "一周内"
    assert count(Post) == 1  # 超过 3 天的被丢弃
    assert count(Hit, Hit.is_backfill.is_(True)) == 1 and count(Alert) == 0
    with session_scope() as db:
        assert db.scalar(select(CrawlState.backfill_done)) is True


def test_similar_posts_alert_once(env):
    setup_group()
    mark_backfilled("冷萃挂耳")
    env.crawler.pages["冷萃挂耳"] = [[
        note(1, "避雷！冷萃挂耳这批喝出一股酸败味", "上周买的冷萃挂耳拆了三包都有怪味，太失望了"),
        note(2, "避雷！冷萃挂耳这批喝出一股酸败味！", "上周买的冷萃挂耳拆了三包都有怪味，太失望了"),
    ]]
    pipeline.run_due(env.services)
    assert count(Hit) == 2 and count(Alert) == 1
    with session_scope() as db:
        groups = set(db.scalars(select(Post.similar_group_id)))
    assert len(groups) == 1


def test_quiet_hours_queue_then_digest(env, monkeypatch):
    setup_group()
    mark_backfilled("冷萃挂耳")
    quiet = {"on": True}
    monkeypatch.setattr("app.alerts.service.in_quiet_hours", lambda n, tz, now=None: quiet["on"])
    env.crawler.pages["冷萃挂耳"] = [[note(1, "避雷冷萃挂耳", "失望"), note(2, "冷萃挂耳售后差评", "踢皮球 投诉")]]
    pipeline.run_due(env.services)
    assert count(Alert, Alert.status == "queued") == 2 and env.hooks.requests == []
    quiet["on"] = False
    pipeline.run_due(env.services)
    assert count(Alert, Alert.status == "sent") == 2 and len(env.hooks.requests) == 1
    assert "共 2 条" in json.loads(env.hooks.requests[0].content)["markdown"]["content"]


def test_auth_error_blocks_crawling(env):
    from app.crawlers.base import CrawlerAuthError

    setup_group()

    def boom(*a, **k):
        raise CrawlerAuthError("TikHub 返回 401")

    env.crawler.search = boom
    pipeline.run_due(env.services)
    with session_scope() as db:
        assert get_crawler_status(db)["auth_failed"] is True
        assert pipeline.due_jobs(db, env.services.settings)  # 仍到期
        assert pipeline.crawler_blocked(db) == "数据源授权失效"


def test_rematch_group_uses_existing_posts(env):
    setup_group()
    mark_backfilled("冷萃挂耳")
    env.crawler.pages["冷萃挂耳"] = [[note(1, "冷萃挂耳和燕麦拿铁", "都不错")]]
    pipeline.run_due(env.services)
    with session_scope() as db:
        g = KeywordGroup(name="燕麦", words=["燕麦拿铁"], exclude_words=[], platforms=["xhs"])
        db.add(g)
        db.flush()
        gid = g.id
    assert pipeline.rematch_group(gid, env.services) == 1
    assert count(Hit, Hit.group_id == gid, Hit.is_backfill.is_(True)) == 1


def test_mock_crawler_end_to_end(env):
    from app.crawlers.mock import MockXhsCrawler

    setup_group(words=["山岚咖啡"])
    env.services.crawler = MockXhsCrawler(interval_min=10)
    pipeline.run_due(env.services)
    assert count(Post) > 0 and count(Hit) > 0


def test_mock_crawler_first_page_never_empty():
    from app.crawlers.mock import MockXhsCrawler

    page = MockXhsCrawler(interval_min=10).search("全嘻嘻")
    assert len(page.notes) == 3 and all(n.published_at <= utcnow() for n in page.notes)
