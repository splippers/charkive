from __future__ import annotations

import json
import os
import threading
import time as _time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jinja2
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from charkive import db as ckdb
from charkive import curation, sanitorium, sandwich
from charkive import sanity as sanity_runner
from charkive.config import load_config, BrickCfg, CharkiveConfig

_SCAN_PROGRESS: dict[str, Any] = {"running": False, "scan_id": None, "message": ""}

_config: CharkiveConfig | None = None
_PKG_DIR = Path(__file__).parent.resolve()

_jinja_env: jinja2.Environment | None = None


def _render(name: str, **ctx: Any) -> str:
    global _jinja_env
    if _jinja_env is None:
        template_dir = str(_PKG_DIR / "web" / "templates")
        _jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_dir),
            autoescape=True,
        )
    template = _jinja_env.get_template(name)
    return template.render(**ctx)


def _get_config() -> CharkiveConfig:
    global _config
    if _config is not None:
        return _config
    base = Path.cwd()
    candidate = base / ".charkive.yml"
    if candidate.is_file():
        _config = load_config(candidate)
        return _config
    p = base
    for _ in range(10):
        p = p.parent
        candidate = p / ".charkive.yml"
        if candidate.is_file():
            _config = load_config(candidate)
            return _config
    raise HTTPException(status_code=404, detail="No .charkive.yml found. Run `charkive init <ROOT>` first.")


def _reload_config() -> CharkiveConfig:
    global _config
    _config = None
    return _get_config()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    static_dir = _PKG_DIR / "web" / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    yield


app = FastAPI(title="Charkive Web", version="1.0.0", lifespan=_lifespan)


def _as_iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=UTC).isoformat(timespec="seconds")


def _fmt_bytes(n: float | int) -> str:
    return sandwich.fmt_bytes(n)


def _summarize(cfg: CharkiveConfig, conn, scan_id: int) -> dict:
    return ckdb.summary_for_scan(conn, scan_id)


def _tier_weight_sort_key(item: tuple[str, Any]) -> int:
    order = {"shyte": 1, "kiloshyte": 5, "megashyte": 10, "gigashyte": 11}
    return order.get(item[0].lower(), 99)


def _fmt_duration(started: float, finished: float | None) -> str:
    end = finished if finished is not None else _time.time()
    secs = end - started
    if secs < 60:
        return f"{secs:.0f}s"
    return f"{secs / 60:.1f}m"


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    return HTMLResponse(_render("dashboard.html", active_page="dashboard"))


@app.get("/scans", response_class=HTMLResponse)
async def scans_page():
    return HTMLResponse(_render("scans.html", active_page="scans"))


@app.get("/scans/{scan_id}", response_class=HTMLResponse)
async def scan_detail_page(scan_id: int):
    return HTMLResponse(_render("scan_detail.html", active_page="scans", scan_id=scan_id))


@app.get("/sanitorium", response_class=HTMLResponse)
async def sanitorium_page():
    return HTMLResponse(_render("sanitorium.html", active_page="sanitorium"))


@app.get("/curation", response_class=HTMLResponse)
async def curation_page():
    return HTMLResponse(_render("curation.html", active_page="curation"))


@app.get("/config", response_class=HTMLResponse)
async def config_page():
    return HTMLResponse(_render("config.html", active_page="config"))


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@app.get("/api/status")
async def api_status():
    cfg = _get_config()
    db_path = cfg.state_db_path()
    conn = ckdb.connect(db_path)
    latest = ckdb.latest_scan(conn)
    san_root = cfg.sanitorium_absolute()
    san_weeks: list[str] = []
    if san_root.is_dir():
        san_weeks = sorted(
            [d.name for d in san_root.iterdir() if d.is_dir() and d.name.count("-W") == 1]
        )
    result: dict[str, Any] = {
        "charkive_version": "1.0.0",
        "config_root": str(cfg.root),
        "sandbox": cfg.sandbox,
        "sanitorium_path": str(san_root),
        "sanitorium_weeks": san_weeks,
        "gluster_volume": cfg.gluster.volume,
        "spinal_tap": cfg.spinal_tap_mode,
        "sanctuary_patterns": list(cfg.sanctuary),
        "rule_count": len(cfg.sanity_rules),
        "scan_running": _SCAN_PROGRESS.get("running", False),
    }
    if latest:
        s_id, finished = latest
        summary = _summarize(cfg, conn, s_id)
        scan_row = conn.execute(
            "SELECT started_at, finished_at, artifact_count, root FROM scans WHERE id=?",
            (s_id,),
        ).fetchone()
        started = float(scan_row[0]) if scan_row else 0
        fin = float(scan_row[1]) if scan_row and scan_row[1] else None
        result["latest_scan"] = {
            "id": s_id,
            "started_at": _as_iso(started),
            "finished_at": _as_iso(fin),
            "duration": _fmt_duration(started, fin),
            "root": str(scan_row[3]) if scan_row else "",
            "artifact_count": int(scan_row[2]) if scan_row else 0,
            "summary": summary,
        }
    else:
        result["latest_scan"] = None
    conn.close()
    return result


@app.get("/api/scans")
async def api_scans_list():
    cfg = _get_config()
    conn = ckdb.connect(cfg.state_db_path())
    rows = conn.execute(
        "SELECT id, started_at, finished_at, artifact_count, root FROM scans ORDER BY id DESC LIMIT 50"
    ).fetchall()
    scans = []
    for r in rows:
        sid = int(r[0])
        started = float(r[1])
        finished = float(r[2]) if r[2] else None
        summary = None
        if finished is not None:
            try:
                summary = _summarize(cfg, conn, sid)
            except Exception:
                pass
        scans.append(
            {
                "id": sid,
                "started_at": _as_iso(started),
                "finished_at": _as_iso(finished),
                "duration": _fmt_duration(started, finished),
                "artifact_count": int(r[3]),
                "root": str(r[4]),
                "summary": summary,
            }
        )
    conn.close()
    return {"scans": scans}


@app.get("/api/scans/{scan_id}")
async def api_scan_detail(scan_id: int):
    cfg = _get_config()
    conn = ckdb.connect(cfg.state_db_path())
    row = conn.execute(
        "SELECT id, started_at, finished_at, artifact_count, root FROM scans WHERE id=?",
        (scan_id,),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Scan not found")
    started = float(row[1])
    finished = float(row[2]) if row[2] else None
    summary = _summarize(cfg, conn, scan_id) if finished else None
    result = {
        "id": int(row[0]),
        "started_at": _as_iso(started),
        "finished_at": _as_iso(finished),
        "duration": _fmt_duration(started, finished),
        "artifact_count": int(row[3]),
        "root": str(row[4]),
        "summary": summary,
    }
    conn.close()
    return result


@app.get("/api/scans/{scan_id}/artifacts")
async def api_scan_artifacts(
    scan_id: int,
    status: str | None = Query(None),
    tier: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
):
    cfg = _get_config()
    conn = ckdb.connect(cfg.state_db_path())
    row = conn.execute("SELECT 1 FROM scans WHERE id=?", (scan_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Scan not found")

    where = ["scan_id=?"]
    params: list[Any] = [scan_id]
    if status:
        where.append("status=?")
        params.append(status)
    if tier:
        where.append("tier=?")
        params.append(tier.lower())
    if search:
        where.append("rel_path LIKE ?")
        params.append(f"%{search}%")

    wsql = " AND ".join(where)
    total_row = conn.execute(
        f"SELECT COUNT(*) FROM artifacts WHERE {wsql}", params
    ).fetchone()
    total = int(total_row[0]) if total_row else 0

    rows = conn.execute(
        f"SELECT id, rel_path, bytes, status, tier, rule_name, mtime, partial_hash FROM artifacts WHERE {wsql} ORDER BY bytes DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    artifacts = []
    for r in rows:
        artifacts.append(
            {
                "id": int(r[0]),
                "rel_path": str(r[1]),
                "bytes": int(r[2]),
                "bytes_fmt": _fmt_bytes(r[2]),
                "status": str(r[3]),
                "tier": str(r[4]) if r[4] else None,
                "rule_name": str(r[5]) if r[5] else None,
                "mtime": _as_iso(r[6]) if r[6] else None,
                "partial_hash": str(r[7]) if r[7] and len(str(r[7])) > 4 else None,
            }
        )
    conn.close()
    return {"total": total, "artifacts": artifacts, "limit": limit, "offset": offset}


@app.post("/api/scan/run")
async def api_run_scan():
    cfg = _get_config()
    if _SCAN_PROGRESS.get("running", False):
        raise HTTPException(status_code=409, detail="Scan already in progress")

    def _run():
        global _SCAN_PROGRESS
        _SCAN_PROGRESS["running"] = True
        _SCAN_PROGRESS["message"] = "Scanning..."
        try:
            scan_id, stats = sanity_runner.run_scan(cfg, do_hash=True)
            _SCAN_PROGRESS["scan_id"] = scan_id
            _SCAN_PROGRESS["message"] = f"Scan #{scan_id} complete ({stats.unreadable_dir} dirs skipped)"
        except Exception as exc:
            _SCAN_PROGRESS["message"] = f"Error: {exc}"
        finally:
            _SCAN_PROGRESS["running"] = False

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "started", "message": "Scan initiated"}


@app.get("/api/scan/progress")
async def api_scan_progress():
    return dict(_SCAN_PROGRESS)


@app.get("/api/sanitorium")
async def api_sanitorium():
    cfg = _get_config()
    lines = sanitorium.list_contents(cfg, depth=3, limit_dirs=100)
    san_root = cfg.sanitorium_absolute()
    weeks: list[dict[str, Any]] = []
    if san_root.is_dir():
        for d in sorted(san_root.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            files: list[dict[str, Any]] = []
            for f in d.rglob("*"):
                if f.is_file() and f.name != "manifest.ndjson":
                    size = f.stat().st_size
                    rel = f.relative_to(san_root)
                    files.append(
                        {
                            "name": f.name,
                            "rel_path": rel.as_posix(),
                            "bytes": size,
                            "bytes_fmt": _fmt_bytes(size),
                        }
                    )
            if files or (d / "manifest.ndjson").exists():
                total_bytes = sum(f["bytes"] for f in files)
                weeks.append(
                    {
                        "week": d.name,
                        "file_count": len(files),
                        "total_bytes": total_bytes,
                        "total_fmt": _fmt_bytes(total_bytes),
                        "files": sorted(files, key=lambda x: x["bytes"], reverse=True),
                    }
                )
    return {"weeks": weeks, "path": str(san_root)}


@app.post("/api/sanitise")
async def api_sanitise(payload: dict[str, Any]):
    cfg = _get_config()
    tier = payload.get("tier")
    dry_run = payload.get("dry_run", True)
    if not dry_run:
        _forbid_if_readonly()
    conn = ckdb.connect(cfg.state_db_path())
    latest = ckdb.latest_scan(conn)
    if not latest:
        conn.close()
        raise HTTPException(status_code=400, detail="No scans available")
    scan_id = int(latest[0])
    try:
        staged, moved_bytes = sanitorium.sanitise_moves(
            cfg, conn, scan_id=scan_id, tier=tier, dry_run=dry_run
        )
    except Exception as exc:
        conn.close()
        raise HTTPException(status_code=500, detail=str(exc))
    conn.close()
    return {
        "staged": len(staged),
        "moved_bytes": moved_bytes,
        "moved_fmt": _fmt_bytes(moved_bytes),
        "dry_run": dry_run,
    }


@app.post("/api/quench")
async def api_quench(payload: dict[str, Any]):
    cfg = _get_config()
    _forbid_if_readonly()
    rel_path = payload.get("path", "")
    if not rel_path:
        raise HTTPException(status_code=400, detail="Missing 'path'")
    try:
        sanitorium.quench(cfg, rel_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "restored", "path": rel_path}


@app.get("/api/config")
async def api_config():
    cfg = _get_config()
    raw = {}
    try:
        raw_text = cfg.source_file.read_text(encoding="utf-8")
    except Exception:
        raw_text = ""
    return {
        "root": str(cfg.root),
        "sandbox": cfg.sandbox,
        "sanitorium_path": str(cfg.sanitorium.relative_path),
        "sanitorium_retention_days": cfg.sanitorium.retention_days,
        "sanctuary": list(cfg.sanctuary),
        "protect_extensions": sorted(cfg.protect_extensions),
        "gluster_volume": cfg.gluster.volume,
        "spinal_tap_mode": cfg.spinal_tap_mode,
        "rule_count": len(cfg.sanity_rules),
        "source_file": str(cfg.source_file),
        "has_brick_protection": cfg.brick.enabled,
        "raw_yaml": raw_text,
    }


@app.post("/api/config/reload")
async def api_config_reload():
    _reload_config()
    return {"status": "reloaded"}


def _forbid_if_readonly() -> None:
    """CHARKIVE_READONLY=1 blocks every call that moves files (sanitise for real, quench)."""
    if os.environ.get("CHARKIVE_READONLY"):
        raise HTTPException(status_code=403, detail="Charkive is running read-only (CHARKIVE_READONLY)")


_CURATION_PROGRESS: dict[str, Any] = {"running": False, "message": ""}


@app.post("/api/curation/run")
async def api_curation_run():
    cfg = _get_config()
    if _CURATION_PROGRESS["running"]:
        raise HTTPException(status_code=409, detail="Curation already running")

    def _run():
        _CURATION_PROGRESS["running"] = True
        try:
            def note(m: str) -> None:
                _CURATION_PROGRESS["message"] = m
            curation.save(cfg, curation.run(cfg, note))
        except Exception as exc:
            _CURATION_PROGRESS["message"] = f"Error: {exc}"
        finally:
            _CURATION_PROGRESS["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started"}


@app.get("/api/curation/progress")
async def api_curation_progress():
    return dict(_CURATION_PROGRESS)


@app.get("/api/curation")
async def api_curation():
    cfg = _get_config()
    return {"running": _CURATION_PROGRESS["running"], "report": curation.load(cfg)}


def start_web_server(host: str = "127.0.0.1", port: int = 8080, config_path: str | None = None):
    import uvicorn

    if config_path:
        global _config
        _config = load_config(Path(config_path))
    uvicorn.run(app, host=host, port=port, log_level="info")
