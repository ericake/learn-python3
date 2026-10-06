import os
import sys
from pathlib import Path

os.environ.update({
    "ENABLE_SCHEDULER": "false",
    "TIKHUB_API_KEY": "",
    "LLM_API_KEY": "",
    "DATABASE_URL": "sqlite:///:memory:",
    "DEFAULT_KEYWORDS": "",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
import pytest  # noqa: E402

from app import db as dbmod  # noqa: E402
from app.alerts.service import Notifier  # noqa: E402
from app.analysis.sentiment import RuleSentimentClassifier  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.crawlers.base import NoteData, SearchPage  # noqa: E402
from app.jobs import pipeline  # noqa: E402


class FakeCrawler:
    """按页返回预先放好的笔记，并记录调用。"""
    platform = "xhs"

    def __init__(self):
        self.pages: dict[str, list[list[NoteData]]] = {}
        self.calls: list[tuple] = []

    def search(self, keyword, page=1, search_id=None, time_filter="一天内"):
        self.calls.append((keyword, page, time_filter))
        pages = self.pages.get(keyword, [])
        notes = pages[page - 1] if page <= len(pages) else []
        return SearchPage(notes=notes, search_id="sid-1", has_more=page < len(pages))


class WebhookRecorder:
    def __init__(self):
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if "qyapi" in str(request.url):
            return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
        return httpx.Response(200, json={"code": 0, "msg": "success"})


@pytest.fixture()
def env(tmp_path):
    dbmod.reset_engine(f"sqlite:///{tmp_path / 'test.db'}")
    dbmod.init_db()
    crawler = FakeCrawler()
    hooks = WebhookRecorder()
    notifier = Notifier(get_settings(), client=httpx.Client(transport=httpx.MockTransport(hooks.handler)),
                        sleep=lambda s: None)
    services = pipeline.Services(settings=get_settings(), crawler=crawler, classifier=RuleSentimentClassifier(),
                                 notifier=notifier)
    pipeline.set_services(services)
    yield type("Env", (), {"crawler": crawler, "hooks": hooks, "services": services})
    pipeline.set_services(None)
