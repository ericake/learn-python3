import json

import httpx

from app.analysis.matcher import match_group
from app.analysis.sentiment import Example, LlmSentimentClassifier, RuleSentimentClassifier, parse_result
from app.analysis.simhash import is_similar, normalize, simhash
from app.config import Settings


def test_match_group_rules():
    words, ex = ["山岚咖啡", "山岚 门店"], ["山岚雾气"]
    assert match_group("今天去了山岚咖啡", "", words, ex) == "山岚咖啡"
    assert match_group("", "山岚的静安门店很出片", words, ex) == "山岚 门店"
    assert match_group("山岚咖啡", "山岚雾气很美", words, ex) is None
    assert match_group("山岚", "", words, ex) is None
    assert match_group("Shanlan COFFEE", "", ["shanlan coffee"], []) == "shanlan coffee"


def test_similarity():
    def item(t, c):
        return simhash(t, c), normalize(t, c)

    a = item("避雷！冷萃挂耳这批喝出一股酸败味", "上周买的山岚冷萃挂耳，拆了三包都有怪味，客服说是正常风味")
    b = item("避雷!!冷萃挂耳这批喝出一股酸败味", "上周买的山岚冷萃挂耳，拆了三包都有怪味。客服说是正常风味")
    b2 = item("避雷！冷萃挂耳这批喝出一股酸败味道", "上周买的山岚冷萃挂耳，拆了三包都有怪味，客服说是正常风味")
    c = item("静安这家门店太出片了", "二楼靠窗位置阳光很好，店员会主动推荐豆子")
    assert is_similar(*a, *b) and is_similar(*a, *b2)
    assert not is_similar(*a, *c)
    assert 0 < a[0] < 2 ** 63


def test_parse_result():
    assert parse_result('{"sentiment":"neg","confidence":0.92,"reason":"投诉怪味"}').sentiment == "neg"
    assert parse_result('```json\n{"sentiment":"POS","confidence":"0.8"}\n```').sentiment == "pos"
    assert parse_result('{"sentiment":"angry"}') is None
    assert parse_result("not json") is None


def test_deepseek_request_and_response():
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        content = json.dumps({"sentiment": "neg", "confidence": 0.9, "reason": "产品有怪味"}, ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})

    s = Settings(llm_api_key="sk-test", llm_model="deepseek-chat")
    clf = LlmSentimentClassifier(s, client=httpx.Client(base_url="https://api.deepseek.com",
                                                        transport=httpx.MockTransport(handler)), sleep=lambda x: None)
    r = clf.classify("产品词", "冷萃挂耳", "避雷", "有怪味", [Example("很好喝", "pos")])
    assert r.sentiment == "neg" and r.confidence == 0.9
    req = seen[0]
    body = json.loads(req.content)
    assert req.url.path == "/chat/completions" and req.headers["Authorization"] == "Bearer sk-test"
    assert body["model"] == "deepseek-chat" and body["response_format"] == {"type": "json_object"}
    assert "很好喝" in body["messages"][1]["content"]


def test_deepseek_failure_returns_none():
    s = Settings(llm_api_key="sk-test")
    clf = LlmSentimentClassifier(s, client=httpx.Client(base_url="https://x", transport=httpx.MockTransport(
        lambda r: httpx.Response(500, text="boom"))), sleep=lambda x: None)
    assert clf.classify("g", "w", "t", "c") is None


def test_rule_classifier():
    clf = RuleSentimentClassifier()
    assert clf.classify("g", "w", "避雷", "太失望了").sentiment == "neg"
    assert clf.classify("g", "w", "", "强烈推荐，回购").sentiment == "pos"
    assert clf.classify("g", "w", "", "不推荐").sentiment == "neg"
    assert clf.classify("g", "w", "", "今天喝了咖啡").sentiment == "neu"
