import time
import networkx as nx
from fastapi.testclient import TestClient
import api.main as main
import engine.pipeline as pipeline
from tests.fixtures import X_PAGE, iso, planted_response, write_json, x_post
from engine.schema import Campaign


def test_production_requires_basic_auth(monkeypatch):
    monkeypatch.setattr(main, "APP_ENV", "production")
    monkeypatch.setattr(main, "APP_AUTH_USERNAME", "demo-user")
    monkeypatch.setattr(main, "APP_AUTH_PASSWORD", "test-password")

    with TestClient(main.app) as client:
        assert client.get("/_health").json() == {"status": "ok"}
        assert client.get("/").status_code == 401
        assert client.get("/api/status").status_code == 401
        assert client.get("/api/status", headers={"Authorization": "Basic !!!"}).status_code == 401
        assert client.get("/api/status", auth=("demo-user", "wrong-password")).status_code == 401
        response = client.get("/api/status", auth=("demo-user", "test-password"))
        assert response.status_code == 200


def test_production_fails_closed_without_auth_config(monkeypatch):
    monkeypatch.setattr(main, "APP_ENV", "production")
    monkeypatch.setattr(main, "APP_AUTH_USERNAME", "")
    monkeypatch.setattr(main, "APP_AUTH_PASSWORD", "")

    with TestClient(main.app) as client:
        assert client.get("/_health").status_code == 200
        assert client.get("/api/status").status_code == 503


def test_upload_analyse_delete(tmp_path, monkeypatch):
    # keep the real data/runs untouched
    monkeypatch.setattr(main, "RUNS", tmp_path)
    monkeypatch.setattr(pipeline, "RUNS", tmp_path)

    with TestClient(main.app) as c:
        response, _ = planted_response()
        with open(write_json(tmp_path / "search.json", response), "rb") as f:
            up = c.post("/api/datasets", files={"file": ("..\\..\\evil.json", f, "application/json")}).json()
        ds = up["dataset_id"]
        assert (tmp_path / ds / "upload.json").exists()  # the X API file as uploaded; client filename never used as a path
        assert (tmp_path / ds / "x.db").exists() and up["posts"] == len(response["data"]) and up["format"] == "X API v2"

        # analysis runs in the background and reports named steps
        assert c.post(f"/api/datasets/{ds}/analyze").status_code == 202
        for _ in range(180):
            job = c.get(f"/api/datasets/{ds}/job").json()
            if job["state"] != "running":
                break
            time.sleep(1)
        assert job["state"] == "done", job

        listed = {d["id"]: d for d in c.get("/api/datasets").json()}
        assert listed[ds]["analyzed"] and listed[ds]["name"] == "evil.json"

        campaigns = c.get(f"/api/datasets/{ds}/campaigns").json()
        assert [x["id"] for x in campaigns] == ["c1", "c2"]
        assert "post_ids" not in campaigns[0] and campaigns[0]["assessment"] is None
        assert c.get(f"/api/datasets/{ds}/campaigns/c1").json()["sample_posts"]
        assert c.get(f"/api/datasets/{ds}/campaigns/c1/verdict").status_code == 404  # never calls Bob

        # the Posts view: every post, filtered; and the at-a-glance numbers
        stats = c.get(f"/api/datasets/{ds}/stats").json()
        assert stats["posts"] == up["posts"] and stats["platforms"] == {"x": up["posts"]} and "hi" in stats["languages"]
        found = c.get(f"/api/datasets/{ds}/posts", params={"campaign": "c1", "limit": 5}).json()
        assert 0 < len(found["posts"]) <= 5 and all(x["campaign"] == "c1" for x in found["posts"])
        assert found["facets"]["campaign"] == {"c1": found["total"]}

        assert c.get("/api/datasets/bad.id/graph").status_code == 400
        assert c.delete(f"/api/datasets/{ds}").status_code == 200
        assert not (tmp_path / ds).exists()


def test_classify_sends_all_stored_sample_posts(monkeypatch):
    campaign = Campaign(
        id="c1", accounts=["a1"], post_ids=[f"p{i}" for i in range(20)],
        size=1, score=50, features={}, signals=[], first_seen=0, last_seen=19,
    )
    samples = [
        {"post_id": f"p{i}", "account_id": "a1", "username": "user",
         "created_at": i, "text": f"post {i}"}
        for i in range(20)
    ]
    received = []

    class Verdict:
        def model_dump(self):
            return {"threat_type": "benign_coordination"}

    def fake_classify(run_dir, campaign_arg, sample_posts):
        received.extend(sample_posts)
        return Verdict(), 0.01, False

    monkeypatch.setattr(main, "load_campaign", lambda *_: campaign)
    monkeypatch.setattr(main, "load_samples", lambda *_: samples)
    monkeypatch.setattr(main, "classify", fake_classify)
    monkeypatch.setattr(main, "escalate", lambda *_: {"level": "LOW"})

    with TestClient(main.app) as client:
        response = client.post("/api/datasets/test/campaigns/c1/classify")

    assert response.status_code == 200
    assert len(received) == 20
    assert received[-1].post_id == "p19"


def test_stream_api_uses_event_time_window_and_marks_alert_provisional(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "STREAM_DB", tmp_path / "streams.sqlite")
    monkeypatch.setattr(main, "STREAMS", tmp_path / "stream-work")
    monkeypatch.setattr(main, "STREAM_WINDOW_SECONDS", 60)
    monkeypatch.setattr(main, "STREAM_RETENTION_SECONDS", 1000)
    observed = []

    def fake_graph(posts, **kwargs):
        observed.append([post.created_at for post in posts])
        return nx.Graph()

    monkeypatch.setattr(main, "build_graph", fake_graph)
    monkeypatch.setattr(main, "find_campaigns", lambda *args, **kwargs: [])

    with TestClient(main.app) as client:
        line = lambda pid, author, t, text: {"data": x_post(pid, author, t, text), "matching_rules": [{"id": "1"}]}
        late, first, old = line("2", "a2", 120, "second post"), line("1", "a1", 90, "first post"), line("0", "a0", 10, "old post")
        response = client.post("/api/streams/alpha/posts", json=late)
        assert response.status_code == 200
        assert response.json()["alert"]["status"] == "provisional"
        assert response.json()["alert"]["review_required"] is True
        client.post("/api/streams/alpha/posts", json=first)
        duplicate = client.post("/api/streams/alpha/posts", json=first)
        assert duplicate.json()["duplicate"] is True
        client.post("/api/streams/alpha/posts", json=old)

        alert = client.get("/api/streams/alpha/alerts").json()
        assert alert["window_posts"] == 2
        assert alert["retained_posts"] == 3
        assert observed[-1] == [90, 120]
        assert client.get("/api/streams/alpha/timeline").json()["points"]
        batch = client.post("/api/streams/beta/posts", json=[late, first])  # a list is one rebuild
        assert batch.json()["posts"] == 2 and observed[-1] == [90, 120]
        assert client.post("/api/streams/alpha/close").json()["status"] == "closed"
        assert client.post("/api/streams/alpha/posts", json=line("3", "a2", 120, "third")).status_code == 409


def test_upload_accepts_only_x_api_v2_json(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RUNS", tmp_path)
    with TestClient(main.app) as c:
        csv = c.post("/api/datasets", files={"file": ("posts.csv", b"post_id,account_id\n1,a", "text/csv")})
        assert csv.status_code == 422 and ".json" in csv.json()["detail"]
        flat = c.post("/api/datasets", files={"file": ("rows.json", b'[{"post_id": "1", "account_id": "a"}]', "application/json")})
        assert flat.status_code == 422 and "Not X API v2 data" in flat.json()["detail"]
        no_time = c.post("/api/datasets", files={"file": ("x.json", b'{"data": [{"id": "1", "text": "x", "author_id": "a"}]}',
                                                          "application/json")})
        assert no_time.status_code == 422 and "created_at" in no_time.json()["detail"]
        assert c.get("/api/datasets").json() == []  # nothing half-stored


def test_x_search_connector(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RUNS", tmp_path)
    monkeypatch.setattr(main, "X_BEARER_TOKEN", "test-token")
    asked = {}
    def fake_search(query, token, max_posts):
        asked.update(query=query, token=token)
        return [X_PAGE]
    monkeypatch.setattr(main, "search_recent", fake_search)
    with TestClient(main.app) as c:
        r = c.post("/api/connectors/x/search", json={"query": "#RajpuraBachao"}).json()
        assert asked == {"query": "#RajpuraBachao", "token": "test-token"}
        assert r["posts"] == 3 and r["source"] == "x_api" and r["name"] == "X search: #RajpuraBachao"
        assert (tmp_path / r["dataset_id"] / "upload.jsonl").exists()  # the API pages exactly as returned
        assert (tmp_path / r["dataset_id"] / "x.db").exists()


def test_stream_accepts_x_api_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "STREAM_DB", tmp_path / "streams.sqlite")
    monkeypatch.setattr(main, "STREAMS", tmp_path / "work")
    monkeypatch.setattr(main, "build_graph", lambda posts, **kw: nx.Graph())
    with TestClient(main.app) as c:
        line = {"data": X_PAGE["data"][0], "includes": X_PAGE["includes"], "matching_rules": [{"id": "1"}]}
        r = c.post("/api/streams/xs/posts", json=line).json()
        assert r["posts"] == 1 and r["alert"]["window_posts"] == 1


def test_posts_view_threads_and_real_counts(tmp_path):
    """Replies, reposts and quotes are linked; counts are X's public_metrics when present, else found in the dataset;
    an original that is only in includes.tweets is shown in the repost card but not listed."""
    import json
    from engine.explore import search_posts, thread
    from engine.xstore import build
    run = tmp_path / "r"
    run.mkdir()
    ref = lambda kind, target: {"referenced_tweets": [{"type": kind, "id": target}]}
    data = [x_post("10", "a", 1, "first #tag"), x_post("11", "b", 2, "reply", **ref("replied_to", "10")),
            x_post("12", "c", 3, "reply to reply", **ref("replied_to", "11")),
            x_post("13", "d", 4, "RT @a: first #tag", **ref("retweeted", "10")),
            x_post("14", "e", 5, "RT @a: first #tag", **ref("retweeted", "10")),
            x_post("15", "f", 6, "quoting", **ref("quoted", "10")),
            x_post("16", "g", 7, "popular", public_metrics={"like_count": 9, "retweet_count": 3}),
            x_post("17", "h", 8, "RT @z: outside", **ref("retweeted", "5"))]
    users = [{"id": u, "username": f"user_{u}"} for u in "abcdefghz"]
    context = [x_post("5", "z", 0, "a post from outside the collection")]
    build([{"data": data, "includes": {"users": users, "tweets": context}}], run / "x.db").close()
    (run / "campaigns.json").write_text(json.dumps([{"id": "c1", "post_ids": ["13", "14"]}]), encoding="utf-8")

    result = search_posts(run, limit=50)
    feed = {p["post_id"]: p for p in result["posts"]}
    assert result["total"] == 8 and "5" not in feed  # the context post isn't part of the dataset
    assert feed["10"]["counts"] == {"replies": 1, "reposts": 2, "quotes": 1, "source": "dataset"}
    assert feed["16"]["counts"]["likes"] == 9 and feed["16"]["counts"]["source"] == "platform"
    assert feed["13"]["original"]["post_id"] == "10" and feed["15"]["quoted"]["post_id"] == "10"
    assert feed["17"]["original"]["text"] == "a post from outside the collection"
    assert feed["12"]["replying_to"] == "user_b"
    assert [p["post_id"] for p in search_posts(run, sort="top")["posts"]][:1] == ["16"]
    assert search_posts(run, kind="reposts")["total"] == 3 and search_posts(run, campaign="c1")["total"] == 2

    t = thread(run, "12")
    assert [a["post_id"] for a in t["ancestors"]] == ["10", "11"] and not t["missing_parent"]
    t = thread(run, "10")
    assert [r["post_id"] for r in t["replies"]] == ["11"] and len(t["reposted_by"]) == 2 and t["quotes"][0]["post_id"] == "15"


def test_security_headers_and_protected_datasets(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RUNS", tmp_path)
    monkeypatch.setattr(main, "PROTECTED_DATASET_IDS", {"u_protected"})

    with TestClient(main.app) as c:
        resp = c.get("/_health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"

        del_resp = c.delete("/api/datasets/u_protected")
        assert del_resp.status_code == 403
        assert "protected" in del_resp.json()["detail"].lower()

