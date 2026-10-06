import httpx
import pytest

from app.config import Settings
from app.crawlers.base import CrawlerAuthError, CrawlerRetryableError
from app.crawlers.xiaohongshu import TikHubXhsCrawler, map_note, parse_search_response

# 结构参照常见的小红书 App 搜索返回，真实结构待用 Token 联调确认
SAMPLE = {
    "code": 200,
    "data": {"data": {
        "search_id": "2f5x8abc",
        "has_more": True,
        "items": [
            {"model_type": "note", "note": {
                "id": "6650a1b2c3d4e5f600112233", "title": "避雷！冷萃挂耳喝出酸味", "desc": "拆了三包都有怪味",
                "type": "normal", "timestamp": 1759718400, "liked_count": "1.8万", "comments_count": 412,
                "collected_count": "960", "shared_count": 96, "xsec_token": "ABxyz",
                "user": {"userid": "5e8f", "nickname": "早八续命研究所"}}},
            {"model_type": "hot_query", "hot_query": {"queries": []}},
            {"model_type": "note", "note": {"id": "6650a1b2c3d4e5f600112244", "display_title": "第二篇",
                                            "interact_info": {"liked_count": "23"}, "user": {"nickname": "momo"}}},
        ]}},
}


def make_settings(**kw):
    return Settings(tikhub_api_key="test-token", tikhub_min_interval_ms=0, **kw)


def test_parse_search_response_maps_fields():
    page = parse_search_response(SAMPLE)
    assert page.search_id == "2f5x8abc" and page.has_more is True
    assert len(page.notes) == 2  # 推荐词条目被跳过
    n = page.notes[0]
    assert n.platform_post_id == "6650a1b2c3d4e5f600112233"
    assert n.author_name == "早八续命研究所" and n.like_cnt == 18000 and n.collect_cnt == 960
    assert n.published_at is not None and n.published_at.year == 2025
    assert n.url.endswith("?xsec_token=ABxyz")
    second = page.notes[1]
    assert second.title == "第二篇" and second.like_cnt == 23 and second.published_at is None


def test_map_note_skips_items_without_id():
    assert map_note({"model_type": "ads"}) is None


def test_search_sends_token_and_params():
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        return httpx.Response(200, json=SAMPLE)

    c = TikHubXhsCrawler(make_settings(), client=httpx.Client(base_url="https://api.tikhub.io",
                                                              transport=httpx.MockTransport(handler)))
    page = c.search("冷萃挂耳", page=2, search_id="abc")
    req = seen[0]
    assert req.headers["Authorization"] == "Bearer test-token"
    assert req.url.path == "/api/v1/xiaohongshu/app_v2/search_notes"
    assert req.url.params["keyword"] == "冷萃挂耳" and req.url.params["page"] == "2"
    assert req.url.params["sort_type"] == "time_descending" and req.url.params["search_id"] == "abc"
    assert len(page.notes) == 2


def test_auth_error_stops_immediately():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(401, json={"detail": "invalid token"})

    c = TikHubXhsCrawler(make_settings(), client=httpx.Client(base_url="https://x", transport=httpx.MockTransport(handler)),
                         sleep=lambda s: None)
    with pytest.raises(CrawlerAuthError):
        c.search("a")
    assert len(calls) == 1


def test_retry_on_429_then_success():
    responses = iter([httpx.Response(429), httpx.Response(502), httpx.Response(200, json=SAMPLE)])
    sleeps = []
    c = TikHubXhsCrawler(make_settings(), client=httpx.Client(base_url="https://x",
                                                              transport=httpx.MockTransport(lambda r: next(responses))),
                         sleep=sleeps.append)
    page = c.search("a")
    assert sleeps == [2, 4] and page.request_count == 3


def test_retry_exhausted():
    c = TikHubXhsCrawler(make_settings(), client=httpx.Client(base_url="https://x",
                                                              transport=httpx.MockTransport(lambda r: httpx.Response(503))),
                         sleep=lambda s: None)
    with pytest.raises(CrawlerRetryableError):
        c.search("a")
