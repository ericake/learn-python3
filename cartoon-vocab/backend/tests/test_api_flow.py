import time
import uuid

from conftest import SAMPLE
from fastapi.testclient import TestClient

from app.main import app


def wait_status(c, ep_id, want, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        ep = c.get(f"/api/v1/episodes/{ep_id}").json()
        if ep["status"] in want:
            return ep
        time.sleep(0.05)
    raise AssertionError(f"status stuck at {ep['status']}: {ep.get('error')}")


def answer_all(c, session_id, pkg, wrong=()):
    attempts = []
    for s in pkg["steps"]:
        if "options" not in s:
            continue
        bad = s["item"] in wrong
        chosen = next(o for o in s["options"] if o != s["answer"]) if bad else s["answer"]
        attempts.append({"client_attempt_id": uuid.uuid4().hex, "vocab_item_id": s["item"], "question_type": s["type"],
                         "option_ids": s["options"], "chosen_id": chosen, "is_correct": not bad,
                         "is_first_try": True, "latency_ms": 1200})
    r = c.post(f"/api/v1/sessions/{session_id}/attempts", json=attempts)
    assert r.status_code == 200
    # 重复上报（离线补传）应当幂等
    assert c.post(f"/api/v1/sessions/{session_id}/attempts", json=attempts).json()["accepted"] == 0
    return attempts


def test_full_parent_and_child_flow():
    with TestClient(app) as c:
        assert c.get("/api/v1/home").json()["episode"] is None

        ep = c.post("/api/v1/episodes", json={"show_name": "Peppa Pig", "season": 1, "episode_no": 1,
                                              "title": "Muddy Puddles"}).json()
        r = c.put(f"/api/v1/episodes/{ep['id']}/transcript", data={"text": "Hi."})
        assert r.status_code == 422

        r = c.put(f"/api/v1/episodes/{ep['id']}/transcript",
                  files={"file": ("ep1.srt", SAMPLE.read_bytes(), "text/plain")})
        assert r.status_code == 202
        ep = wait_status(c, ep["id"], {"reviewing", "failed"})
        assert ep["status"] == "reviewing", ep["error"]
        selected = [i for i in ep["items"] if i["selected"]]
        backups = [i for i in ep["items"] if not i["selected"]]
        assert len(selected) == 10 and backups

        # 家长审核：取消一个、换上一个备选、手动加一个
        c.patch(f"/api/v1/episodes/{ep['id']}/items/{selected[-1]['id']}", json={"selected": False})
        c.patch(f"/api/v1/episodes/{ep['id']}/items/{backups[0]['id']}", json={"selected": True})
        r = c.post(f"/api/v1/episodes/{ep['id']}/items", json={"text": "grass"})
        assert r.status_code == 201 and r.json()["source_sentence"]

        assert c.post(f"/api/v1/episodes/{ep['id']}/confirm").status_code == 202
        ep = wait_status(c, ep["id"], {"ready", "failed"})
        assert ep["status"] == "ready", ep["error"]
        item = next(i for i in ep["items"] if i["selected"])
        assert item["image_url"].startswith("/media/image/")
        assert c.get(item["image_url"]).status_code == 200

        # 换图
        r = c.post(f"/api/v1/episodes/{ep['id']}/items/{item['id']}/regenerate-image")
        assert r.status_code == 200 and r.json()["image_url"] != item["image_url"]
        assert r.json()["image_regen_left"] == 2

        home = c.get("/api/v1/home").json()
        assert home["episode"]["id"] == ep["id"] and not home["episode"]["preview_done"]

        # 直接复习（不强制先预习）：应包含认识卡
        review = c.get(f"/api/v1/lessons/{ep['id']}?mode=review").json()
        assert any(s["type"] == "Q1" for s in review["steps"])

        pkg = c.get(f"/api/v1/lessons/{ep['id']}?mode=preview").json()
        for s in pkg["steps"]:
            for ref in s.get("options", []) + s.get("prompt", []) + s.get("audio", []):
                assert ref in pkg["assets"], ref
        sess = c.post("/api/v1/sessions", json={"episode_id": ep["id"], "mode": "preview"}).json()
        first_word = next(s["item"] for s in pkg["steps"] if s["type"] == "Q3")
        answer_all(c, sess["id"], pkg, wrong={first_word})
        fin = c.post(f"/api/v1/sessions/{sess['id']}/finish").json()
        assert fin["sticker_key"] and fin["streak_days"] == 1
        assert c.post(f"/api/v1/sessions/{sess['id']}/finish").json()["sticker_key"] == fin["sticker_key"]

        review = c.get(f"/api/v1/lessons/{ep['id']}?mode=review").json()
        assert review["steps"][1]["type"] == "warmup"

        assert c.get("/api/v1/home").json()["episode"]["preview_done"]
        rep = c.get(f"/api/v1/reports/episodes/{ep['id']}").json()
        assert rep["preview"]["done"] and not rep["review"]["done"]
        wrong_item = next(i for i in rep["items"] if i["vocab_id"] == first_word)
        assert wrong_item["first_try_correct"] < wrong_item["first_try_total"]
        summary = c.get("/api/v1/reports/summary").json()
        assert summary["streak_days"] == 1 and summary["counts"]["learning"] >= 10
        assert len(c.get("/api/v1/stickers").json()) == 1
