import gc
import base64
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

# Ensure correct MIME types on Windows
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
from fastapi import FastAPI, HTTPException, UploadFile, File, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import (APP_AUTH_PASSWORD, APP_AUTH_USERNAME, APP_ENV, WEB_DIST, RUNS, STREAMS,
                    STREAM_WINDOW_SECONDS, STREAM_RETENTION_SECONDS, MIN_EDGE_WEIGHT, TIME_WINDOW, X_BEARER_TOKEN,
                    DEMO_RUNS, ROOT, DEMO_MODE, MAX_UPLOAD_BYTES, PROTECTED_DATASET_IDS)
from engine.xstore import NotXApiData, ingest, open_db, posts_from_responses, read_posts
from connectors.x_search import XApiError, search_recent
from engine.pipeline import analyze, STAGES
from engine.schema import Campaign, Post
from engine.coordination import build_graph
from engine.campaigns import find_campaigns
from engine.streaming import close as close_stream, ingest as ingest_stream_post, read_state as read_stream_state, save_alert
from engine.escalation import escalate
from engine.zones import dataset_zone, guess_timezone
from engine.explore import dataset_stats, search_posts, thread
from bob.client import BobNotConfigured, cached_verdict, classify, is_bob_configured
from brief.render import render_brief

log = logging.getLogger(__name__)

# ponytail: in-memory job table for this one server process; a restart forgets running jobs (re-run the analysis)
JOBS: dict[str, dict] = {}
UPLOAD_TYPES = (".json", ".jsonl")  # X API v2 JSON only: see engine/xstore.py and docs/data-model.md
STREAM_DB = STREAMS / "streams.sqlite"
STREAM_LOCK = threading.RLock()  # ponytail: one worker process only; the graph is rebuilt from the window on every post


app = FastAPI(title="Social Media Threat Intelligence Engine")


@app.on_event("startup")
def startup_seed_demo_data():
    """Ensure runtime directories exist and auto-seed pre-loaded demonstration datasets on fresh deployments."""
    RUNS.mkdir(parents=True, exist_ok=True)
    STREAMS.mkdir(parents=True, exist_ok=True)

    # Do not auto-seed during automated test runs
    if os.getenv("PYTEST_CURRENT_TEST"):
        return

    try:
        has_datasets = any(d.is_dir() and (d / "x.db").exists() for d in RUNS.iterdir())
    except Exception:
        has_datasets = False

    if not has_datasets and DEMO_RUNS.exists():
        log.info("No datasets detected in %s; seeding pre-loaded demo runs from %s...", RUNS, DEMO_RUNS)
        for d in DEMO_RUNS.iterdir():
            if d.is_dir() and (d / "x.db").exists():
                target = RUNS / d.name
                if not target.exists():
                    shutil.copytree(d, target)
                    log.info("Seeded demo dataset: %s", d.name)


@app.middleware("http")
async def require_deployment_auth(request, call_next):
    if request.url.path == "/_health":
        response = await call_next(request)
    elif DEMO_MODE or APP_ENV in ("demo", "public") or (APP_ENV != "production" and not (APP_AUTH_USERNAME and APP_AUTH_PASSWORD)):
        response = await call_next(request)
    elif not APP_AUTH_USERNAME or not APP_AUTH_PASSWORD:
        return JSONResponse(status_code=503, content={"detail": "Deployment authentication is not configured."})
    else:
        authorization = request.headers.get("authorization", "")
        try:
            scheme, encoded = authorization.split(" ", 1)
            username, password = base64.b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
        except (ValueError, UnicodeDecodeError):
            username = password = ""
            scheme = ""
        valid = (
            scheme.lower() == "basic"
            and hmac.compare_digest(username.encode("utf-8"), APP_AUTH_USERNAME.encode("utf-8"))
            and hmac.compare_digest(password.encode("utf-8"), APP_AUTH_PASSWORD.encode("utf-8"))
        )
        if not valid:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required."},
                headers={"WWW-Authenticate": 'Basic realm="Threat Intelligence Demo", charset="UTF-8"'},
            )
        response = await call_next(request)

    # Inject standard defense-in-depth HTTP security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


@app.get("/_health")
def health():
    return {"status": "ok"}


def run_dir_for(dataset_id: str) -> Path:
    # dataset_id becomes a folder name, so allow only simple IDs (no "..", slashes or drive letters)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", dataset_id):
        raise HTTPException(status_code=400, detail="Invalid dataset id")
    return RUNS / dataset_id


def read_json(path: Path, missing: str):
    if not path.exists():
        raise HTTPException(status_code=404, detail=missing)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def source_file(dataset_id: str, run_dir: Path) -> Path:
    """The file a dataset is analysed from: the upload, or the raw pages of an X search."""
    uploads = sorted(run_dir.glob("upload*"))
    if uploads:
        return uploads[0]
    raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")


def dataset_meta(run_dir: Path) -> dict:
    """Name, counts, clock and ingestion warnings, written to meta.json when the dataset is stored."""
    meta_path = run_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    return {"posts": 0, "accounts": 0, "timezone": "UTC", "warnings": [], **meta}


def load_campaign(run_dir: Path, cid: str) -> Campaign:
    campaigns = read_json(run_dir / "campaigns.json", "Campaigns not found. Run analysis first.")
    target = next((c for c in campaigns if c["id"] == cid), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Campaign {cid} not found")
    return Campaign.model_validate(target)


def load_samples(run_dir: Path, cid: str) -> list[dict]:
    samples_path = run_dir / "samples.json"
    if samples_path.exists():
        samples = read_json(samples_path, "Error reading samples")
        raw = samples.get(cid, [])
    else:
        # Fallback if samples.json does not exist
        posts_path = run_dir / "posts.json"
        camp_path = run_dir / "campaigns.json"
        if not posts_path.exists() or not camp_path.exists():
            return []
        camps = read_json(camp_path, "Error reading campaigns")
        c = next((c for c in camps if c.get("id") == cid), None)
        if not c:
            return []
        acc_set = set(c.get("accounts", []))
        all_posts = read_json(posts_path, "Error reading posts")
        raw = [p for p in all_posts if p.get("account_id") in acc_set][:20]

    result = []
    for p in raw:
        p_dict = dict(p)
        p_bytes = json.dumps({k: v for k, v in p_dict.items() if k not in ("sha256", "sha256_hash")}, sort_keys=True).encode("utf-8")
        h = hashlib.sha256(p_bytes).hexdigest()
        p_dict["sha256"] = h
        p_dict["sha256_hash"] = h
        result.append(p_dict)
    return result


def campaign_summary(c: dict) -> dict:
    """Campaign without its (possibly huge) account and post ID lists."""
    return {**{k: v for k, v in c.items() if k not in ("accounts", "post_ids")}, "post_count": len(c["post_ids"])}


def run_job(dataset_id: str):
    job = JOBS[dataset_id]

    def progress(stage: str):
        job["step"] = STAGES.index(stage)

    try:
        progress("Reading posts")
        run_dir = RUNS / dataset_id
        db = open_db(run_dir)  # the dataset's X database: the posts view is what gets analysed
        try:
            posts = read_posts(db)
        finally:
            db.close()
        result = analyze(dataset_id, posts, progress=progress, zone=dataset_meta(run_dir)["timezone"])
        job.update(state="done", finished=time.time(), campaigns=len(result["campaigns"]), runtime_ms=result["runtime_ms"])
    except Exception as e:
        log.exception("Analysis of %s failed", dataset_id)
        job.update(state="error", error=str(e), finished=time.time())


@app.get("/api/status")
def status():
    return {"bob_configured": is_bob_configured(), "x_configured": bool(X_BEARER_TOKEN), "version": "0.4.0"}


# Rolling-window stream: posts arrive one at a time or in lists; each request re-runs detection on the last STREAM_WINDOW_SECONDS
# of event time and returns a provisional alert. Walkthrough: demo/stream-demo.md.
def validate_stream_id(stream_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", stream_id):
        raise HTTPException(status_code=400, detail="Invalid stream id")
    return stream_id


def recompute_stream(stream_id: str, posts: list[Post], latest: int) -> dict:
    window_start = latest - STREAM_WINDOW_SECONDS
    active_posts = [post for post in posts if window_start <= post.created_at <= latest]
    stream_dir = STREAMS / stream_id
    stream_dir.mkdir(parents=True, exist_ok=True)
    # co-actions still count only within TIME_WINDOW seconds, as in batch analysis; the stream window only limits which posts
    graph = build_graph(active_posts, db_path=stream_dir / "coordination.sqlite", window=TIME_WINDOW, min_weight=MIN_EDGE_WEIGHT)
    gc.collect()  # the toolkit leaves its SQLite connection to the garbage collector; Windows can't delete an open file
    campaigns = find_campaigns(graph, active_posts, min_size=5, window=TIME_WINDOW)
    return {
        "stream_id": stream_id,
        "status": "provisional",
        "review_required": True,
        "window_started_at": window_start,
        "window_ended_at": latest,
        "last_updated_at": time.time(),
        "retained_posts": len(posts),
        "window_posts": len(active_posts),
        "campaigns": [
            {"id": c.id, "accounts": c.size, "post_count": len(c.post_ids), "coordination_score": c.score,
             "signals": c.signals, "top_hashtag": c.top_hashtag, "first_seen": c.first_seen,
             "last_seen": c.last_seen, "detected_at": c.detected_at}
            for c in campaigns
        ],
    }


@app.post("/api/streams/{stream_id}/posts")
def add_stream_post(stream_id: str, payload: dict | list[dict] = Body(...)):
    """X API v2 filtered-stream lines ({"data": {...}, "includes": ..., "matching_rules": ...}) or response pages,
    one or a list (one graph rebuild per request, which takes a few seconds)."""
    validate_stream_id(stream_id)
    rows = payload if isinstance(payload, list) else [payload]
    if not rows or not all(rows):
        raise HTTPException(status_code=422, detail="Post payload cannot be empty")
    try:
        new_posts = posts_from_responses(rows)
    except (ValueError, TypeError, KeyError) as e:
        raise HTTPException(status_code=422, detail=f"Not X API v2 data: {e}")
    with STREAM_LOCK:
        try:
            duplicates = [ingest_stream_post(STREAM_DB, stream_id, p, STREAM_RETENTION_SECONDS) for p in new_posts]
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        _, posts, latest = duplicates[-1]  # the last ingest returns every retained post and the watermark
        alert = recompute_stream(stream_id, posts, latest)
        save_alert(STREAM_DB, stream_id, alert)
    return {"duplicate": all(d for d, _, _ in duplicates), "posts": len(new_posts), "alert": alert}


@app.get("/api/streams/{stream_id}/alerts")
def get_stream_alerts(stream_id: str):
    validate_stream_id(stream_id)
    state = read_stream_state(STREAM_DB, stream_id)
    if not state:
        raise HTTPException(status_code=404, detail="Stream not found")
    return state[0]["alert"]


@app.get("/api/streams/{stream_id}/timeline")
def get_stream_timeline(stream_id: str):
    validate_stream_id(stream_id)
    state = read_stream_state(STREAM_DB, stream_id)
    if not state:
        raise HTTPException(status_code=404, detail="Stream not found")
    stream, posts = state
    buckets: dict[int, int] = {}
    for post in posts:
        if post.created_at >= (stream["latest_event_time"] or 0) - STREAM_WINDOW_SECONDS:
            bucket_time = post.created_at // 60 * 60
            buckets[bucket_time] = buckets.get(bucket_time, 0) + 1
    return {"stream_id": stream_id, "bucket_seconds": 60,
            "points": [{"t": t, "total": count} for t, count in sorted(buckets.items())]}


@app.post("/api/streams/{stream_id}/close")
def finish_stream(stream_id: str):
    validate_stream_id(stream_id)
    if not close_stream(STREAM_DB, stream_id) and not read_stream_state(STREAM_DB, stream_id):
        raise HTTPException(status_code=404, detail="Stream not found")
    return {"stream_id": stream_id, "status": "closed"}


@app.get("/api/datasets")
def list_datasets():
    datasets = []
    for d in sorted(RUNS.iterdir()) if RUNS.exists() else []:
        if not d.is_dir() or not (d / "x.db").exists():
            continue  # every dataset is an X database; anything else in the folder is not a dataset
        try:
            meta = dataset_meta(d)
        except Exception:
            log.exception("Skipping unreadable dataset %s", d.name)
            continue
        datasets.append({
            "id": d.name,
            "name": meta.get("name") or d.name,
            "description": meta.get("description"),
            "towns": meta.get("towns"),   # optional map coordinates {town: [x, y]}; otherwise the map lays towns out itself
            "posts": meta["posts"],
            "accounts": meta["accounts"],
            "timezone": meta["timezone"],
            # results from older versions lack samples.json and must be re-run
            "analyzed": (d / "campaigns.json").exists() and (d / "samples.json").exists(),
            "protected": d.name in PROTECTED_DATASET_IDS or (DEMO_RUNS.exists() and (DEMO_RUNS / d.name).exists()),
            "warnings": meta["warnings"],
            "source": meta.get("source"),
            "fetched_at": meta.get("fetched_at"),
            "job": JOBS.get(d.name, {"state": "idle"}),
        })
    return sorted(datasets, key=lambda d: d.get("fetched_at") or (RUNS / d["id"]).stat().st_mtime, reverse=True)  # newest first


@app.post("/api/datasets")
def upload_dataset(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in UPLOAD_TYPES:
        raise HTTPException(status_code=422, detail=f"Upload one of: {', '.join(UPLOAD_TYPES)}")
    name = Path((file.filename or "upload").replace("\\", "/")).name

    dataset_id = f"u_{uuid.uuid4().hex[:6]}"
    dataset_dir = RUNS / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=True)
    upload_path = dataset_dir / f"upload{suffix}"  # never build paths from the client's filename

    size = 0
    with open(upload_path, "wb") as f:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                f.close()
                shutil.rmtree(dataset_dir, ignore_errors=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"Uploaded file exceeds maximum limit of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
                )
            f.write(chunk)

    try:
        posts, warnings = ingest(upload_path, dataset_dir / "x.db")
    except (NotXApiData, KeyError, TypeError) as e:
        shutil.rmtree(dataset_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=f"Not X API v2 data: {e}")
    return {"dataset_id": dataset_id, **save_meta(dataset_dir, posts, name=name, warnings=warnings)}


def save_meta(run_dir: Path, posts: list[Post], **extra) -> dict:
    meta = {"format": "X API v2", **extra, "posts": len(posts), "accounts": len({p.account_id for p in posts}),
            "timezone": guess_timezone(posts)}
    (run_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta


@app.post("/api/connectors/x/search")
def x_search(body: dict = Body(...)):
    """Pull recent posts matching an X search query (e.g. '#RedFort OR "tractor rally"') into a new dataset."""
    query = str(body.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="Enter a search query")
    if not X_BEARER_TOKEN:
        raise HTTPException(status_code=503, detail="Add X_BEARER_TOKEN to src/.env to search X")
    try:
        pages = search_recent(query, X_BEARER_TOKEN, max_posts=min(int(body.get("max_posts") or 500), 5000))
    except XApiError as e:
        raise HTTPException(status_code=502, detail=str(e))
    dataset_id = f"x_{uuid.uuid4().hex[:6]}"
    run_dir = RUNS / dataset_id
    run_dir.mkdir(parents=True)
    # the API pages exactly as returned are the dataset's source file (one page per line), stored like an upload
    source = run_dir / "upload.jsonl"
    source.write_text("\n".join(json.dumps(pg, ensure_ascii=False) for pg in pages), encoding="utf-8")
    try:
        posts, warnings = ingest(source, run_dir / "x.db")
    except NotXApiData as e:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise HTTPException(status_code=404, detail=f"X returned no usable posts for this query: {e}")
    meta = save_meta(run_dir, posts, name=f"X search: {query}", source="x_api", query=query,
                     fetched_at=int(time.time()), warnings=warnings)
    return {"dataset_id": dataset_id, **meta}


@app.delete("/api/datasets/{dataset_id}")
def delete_dataset(dataset_id: str):
    if dataset_id in PROTECTED_DATASET_IDS or (DEMO_RUNS.exists() and (DEMO_RUNS / dataset_id).exists()):
        raise HTTPException(status_code=403, detail="Demonstration datasets are protected and cannot be deleted.")
    if DEMO_MODE:
        raise HTTPException(status_code=403, detail="Dataset deletion is disabled in public demo mode.")
    run_dir = run_dir_for(dataset_id)
    if JOBS.get(dataset_id, {}).get("state") == "running":
        raise HTTPException(status_code=409, detail="Wait for the analysis to finish")
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    try:
        shutil.rmtree(run_dir)
    except OSError as e:
        raise HTTPException(status_code=409, detail=f"Some files are still in use; try again in a moment ({e.strerror})")
    JOBS.pop(dataset_id, None)
    return {"deleted": dataset_id}


@app.post("/api/datasets/{dataset_id}/analyze", status_code=202)
def start_analysis(dataset_id: str):
    """Starts analysis in the background; poll /job for progress."""
    if not (run_dir_for(dataset_id) / "x.db").exists():
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    
    # Concurrency control: prevent RAM exhaustion on low-memory servers (e.g. 1GB VPS)
    active = [k for k, v in JOBS.items() if v.get("state") == "running" and k != dataset_id]
    if active:
        raise HTTPException(
            status_code=429,
            detail=f"An analysis job for dataset '{active[0]}' is already in progress. Please wait for it to finish."
        )

    if JOBS.get(dataset_id, {}).get("state") != "running":
        JOBS[dataset_id] = {"state": "running", "step": 0, "stages": STAGES, "started": time.time()}
        threading.Thread(target=run_job, args=(dataset_id,), daemon=True).start()
    return JOBS[dataset_id]


@app.get("/api/datasets/{dataset_id}/job")
def job_status(dataset_id: str):
    run_dir_for(dataset_id)
    return JOBS.get(dataset_id, {"state": "idle"})


@app.get("/api/datasets/{dataset_id}/campaigns")
def get_campaigns(dataset_id: str):
    run_dir = run_dir_for(dataset_id)
    campaigns = read_json(run_dir / "campaigns.json", "Campaigns not found. Run analysis first.")
    zone = dataset_zone(run_dir)
    result = []
    for c in campaigns:
        v = cached_verdict(run_dir, c["id"])
        assessment = {"threat_type": v.threat_type, "severity": v.severity,
                      "level": escalate(c["score"], v, zone)["level"],
                      "offline_event": v.offline_event.model_dump() if v.offline_event else None} if v else None
        result.append({**campaign_summary(c), "assessment": assessment})
    return result


@app.get("/api/datasets/{dataset_id}/graph")
def get_graph(dataset_id: str):
    return read_json(run_dir_for(dataset_id) / "graph.json", "Graph not found. Run analysis first.")


@app.get("/api/datasets/{dataset_id}/timeline")
def get_timeline(dataset_id: str):
    return read_json(run_dir_for(dataset_id) / "timeline.json", "Timeline not found. Run analysis first.")


@app.get("/api/datasets/{dataset_id}/stats")
def get_stats(dataset_id: str):
    try:
        return dataset_stats(run_dir_for(dataset_id))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/datasets/{dataset_id}/posts")
def get_posts(dataset_id: str, q: str = "", campaign: str = "", account: str = "", hashtag: str = "",
              platform: str = "", language: str = "", city: str = "", reply_to: str = "", repost_of: str = "",
              quote_of: str = "", kind: str = "", sort: str = "latest", offset: int = 0, limit: int = 50):
    """Search and filter every post of an analysed dataset (the Posts view). sort: latest, oldest or top;
    kind: original, replies, reposts, quotes or media."""
    try:
        return search_posts(run_dir_for(dataset_id), q=q, offset=max(0, offset), limit=min(max(1, limit), 200),
                            sort=sort, kind=kind, campaign=campaign, account=account, hashtag=hashtag,
                            platform=platform, language=language, city=city, reply_to=reply_to,
                            repost_of=repost_of, quote_of=quote_of)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/datasets/{dataset_id}/posts/{post_id}/thread")
def get_thread(dataset_id: str, post_id: str):
    """A post with the posts it replies to, its replies, who reposted it and who quoted it."""
    try:
        return thread(run_dir_for(dataset_id), post_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Post {post_id} is not in this dataset")


@app.get("/api/datasets/{dataset_id}/campaigns/{cid}")
def get_campaign(dataset_id: str, cid: str):
    run_dir = run_dir_for(dataset_id)
    campaign = load_campaign(run_dir, cid).model_dump()
    return {**campaign_summary(campaign), "accounts": campaign["accounts"], "sample_posts": load_samples(run_dir, cid)}


@app.get("/api/datasets/{dataset_id}/campaigns/{cid}/verdict")
def get_verdict(dataset_id: str, cid: str):
    """Cached Bob verdict only; never calls Bob (so selecting a campaign costs nothing)."""
    run_dir = run_dir_for(dataset_id)
    campaign = load_campaign(run_dir, cid)
    verdict = cached_verdict(run_dir, cid)
    if not verdict:
        raise HTTPException(status_code=404, detail="Not classified yet")
    return {"verdict": verdict.model_dump(), "escalation": escalate(campaign.score, verdict, dataset_zone(run_dir)),
            "cached": True, "cost": 0.0}


@app.post("/api/datasets/{dataset_id}/campaigns/{cid}/classify")
def classify_campaign(dataset_id: str, cid: str):
    run_dir = run_dir_for(dataset_id)
    campaign = load_campaign(run_dir, cid)
    sample_posts = [Post.model_validate(p) for p in load_samples(run_dir, cid)[:20]]

    try:
        verdict, cost, is_cached = classify(run_dir, campaign, sample_posts)
    except BobNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # Bob failed or never gave a valid answer
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "verdict": verdict.model_dump(),
        "escalation": escalate(campaign.score, verdict, dataset_zone(run_dir)),
        "cached": is_cached,
        "cost": cost,
    }


@app.get("/api/datasets/{dataset_id}/brief", response_class=HTMLResponse)
def get_brief(dataset_id: str, campaign_id: str | None = None, campaign: str | None = None):
    cid = campaign_id or campaign
    run_dir_for(dataset_id)
    try:
        return HTMLResponse(content=render_brief(dataset_id, campaign_id=cid))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate brief: {e}")


# Frontend static files mounting
if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
else:
    @app.get("/")
    def frontend_missing():
        return HTMLResponse("Frontend not built — run <code>npm ci && npm run build</code> in src/web.")
