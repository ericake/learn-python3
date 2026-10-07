"""真实采集相关：没有 Token 不造数据、切换模式清理演示数据、Key 清洗、.env 写入。"""
import httpx
from sqlalchemy import func, select

from app.config import Settings, get_settings
from app.crawlers.base import NoteData
from app.crawlers.xiaohongshu import TikHubXhsCrawler
from app.db import session_scope, utcnow
from app.jobs import pipeline
from app.main import seed
from app.models import CrawlState, Hit, KeywordGroup, Post
from app.settings_store import get_value, save_value


def test_no_token_means_no_crawler_and_no_jobs(env):
    services = pipeline.build_services(Settings(tikhub_api_key="", crawler_mode="auto"))
    assert services.crawler is None
    with session_scope() as db:
        db.add(KeywordGroup(name="全嘻嘻", words=["全嘻嘻"], exclude_words=[], platforms=["xhs"]))
    assert pipeline.run_due(services) == []
    with session_scope() as db:
        assert pipeline.crawler_blocked(db, services) == "未配置 TikHub Token"
        assert db.scalar(select(func.count(Post.id))) == 0


def test_mock_only_when_explicit():
    assert Settings(tikhub_api_key="", crawler_mode="auto").effective_crawler_mode == "none"
    assert Settings(tikhub_api_key="", crawler_mode="mock").effective_crawler_mode == "mock"
    assert Settings(tikhub_api_key="t", crawler_mode="auto").effective_crawler_mode == "tikhub"


def test_keys_are_stripped():
    s = Settings(tikhub_api_key='  "abc123"\n', llm_api_key=" 'sk-x' ")
    assert s.tikhub_api_key == "abc123" and s.llm_api_key == "sk-x"


def _add_post(db, pid, mock):
    p = Post(platform="xhs", platform_post_id=pid, title="全嘻嘻", content="", raw={"mock": True} if mock else {"id": pid})
    db.add(p)
    db.flush()
    g = db.scalar(select(KeywordGroup)) or KeywordGroup(name="全嘻嘻", words=["全嘻嘻"], exclude_words=[], platforms=["xhs"])
    db.add(g)
    db.flush()
    db.add(Hit(post_id=p.id, group_id=g.id, matched_word="全嘻嘻", sentiment="neu"))


def test_switch_from_mock_purges_demo_data(env):
    with session_scope() as db:
        _add_post(db, "m1", mock=True)
        _add_post(db, "r1", mock=False)
        db.add(CrawlState(platform="xhs", keyword="全嘻嘻", backfill_done=True, last_success_at=utcnow()))
        save_value(db, "data_mode", {"mode": "mock"})
    seed()  # 测试环境没有 Token → mode = none，不是 mock
    with session_scope() as db:
        assert list(db.scalars(select(Post.platform_post_id))) == ["r1"]
        assert db.scalar(select(func.count(Hit.id))) == 1
        assert db.scalar(select(func.count(CrawlState.id))) == 0  # 重新回溯
        assert get_value(db, "data_mode", {})["mode"] == "none"
        db.add(CrawlState(platform="xhs", keyword="全嘻嘻", backfill_done=True))
    seed()  # 再次启动不会重复清理
    with session_scope() as db:
        assert db.scalar(select(func.count(CrawlState.id))) == 1


def test_fetch_raw_returns_payload():
    payload = {"code": 200, "data": {"data": {"items": []}}}
    c = TikHubXhsCrawler(Settings(tikhub_api_key="t", tikhub_min_interval_ms=0),
                         client=httpx.Client(base_url="https://x", transport=httpx.MockTransport(
                             lambda r: httpx.Response(200, json=payload))))
    assert c.fetch_raw("全嘻嘻") == (payload, 1)


def test_non_json_response_is_reported():
    c = TikHubXhsCrawler(Settings(tikhub_api_key="t", tikhub_min_interval_ms=0),
                         client=httpx.Client(base_url="https://x", transport=httpx.MockTransport(
                             lambda r: httpx.Response(200, text="<html>gateway</html>"))))
    try:
        c.search("全嘻嘻")
    except Exception as e:
        assert "不是 JSON" in str(e)
    else:
        raise AssertionError("应当报错")


def test_setup_env_helpers():
    from setup_env import read_value, set_value

    text = "# x\nTIKHUB_API_KEY=\nDEFAULT_KEYWORDS=全嘻嘻            # 注释\n"
    assert read_value(text, "TIKHUB_API_KEY") == "" and read_value(text, "DEFAULT_KEYWORDS") == "全嘻嘻"
    t2 = set_value(text, "TIKHUB_API_KEY", "abc+/=")
    assert read_value(t2, "TIKHUB_API_KEY") == "abc+/=" and t2.count("TIKHUB_API_KEY") == 1
    assert read_value(set_value(text, "LLM_API_KEY", "sk-1"), "LLM_API_KEY") == "sk-1"


def test_status_reports_no_token(env):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        assert get_settings().effective_crawler_mode == "none"
        assert c.get("/api/v1/system/status").json()["state"] in ("no_token", "idle")
