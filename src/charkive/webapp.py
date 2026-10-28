from __future__ import annotations

import ipaddress
import json
import os
import secrets
import threading
import time as _time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jinja2
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

from charkive import db as ckdb
from charkive import curation, sanitorium, sandwich
from charkive import sanity as sanity_runner
from charkive.config import BrickCfg, CharkiveConfig, load_config
from charkive.fire_codes import tier_confirmation, tier_weight
from charkive.paths import forbidden_brick_resolve

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


_basic_auth = HTTPBasic(auto_error=False)


def _require_web_auth(credentials: HTTPBasicCredentials | None = Depends(_basic_auth)) -> None:
    token = os.environ.get("CHARKIVE_WEB_TOKEN")
    if not token:
        return
    valid = (
        credentials is not None
        and secrets.compare_digest(credentials.username.encode(), b"charkive")
        and secrets.compare_digest(credentials.password.encode(), token.encode())
    )
    if not valid:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return host.lower() == "localhost"


app = FastAPI(
    title="Charkive Web",
    version="1.0.0",
    lifespan=_lifespan,
    dependencies=[Depends(_require_web_auth)],
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


_PROXY_HEADERS = ("forwarded", "x-forwarded-for", "x-forwarded-host", "x-real-ip")


def _untrusted_without_token(request: Request) -> bool:
    """True if an unauthenticated request may not come from a local browser.

    A reverse proxy or tunnel on this host makes every request look like
    loopback, so any proxy header means the peer address cannot be trusted.
    """
    peer = request.client.host if request.client else None
    if not _is_loopback_host(peer):
        return True
    return any(name in request.headers for name in _PROXY_HEADERS)


@app.middleware("http")
async def require_local_peer_without_token(request: Request, call_next):
    if not os.environ.get("CHARKIVE_WEB_TOKEN"):
        if _untrusted_without_token(request):
            return JSONResponse(
                {"detail": "Remote Charkive access requires CHARKIVE_WEB_TOKEN"},
                status_code=403,
            )
    return await call_next(request)


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
    _check_brick_protection(cfg)
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
    dry_run = payload.get("dry_run", True)
    if not isinstance(dry_run, bool):
        raise HTTPException(status_code=400, detail="'dry_run' must be true or false")
    tier = _web_tier(payload.get("tier"))
    _check_disk_safety(cfg)
    if not dry_run:
        _forbid_if_readonly()
    conn = ckdb.connect(cfg.state_db_path())
    try:
        latest = ckdb.latest_scan(conn)
        if not latest:
            raise HTTPException(status_code=400, detail="No scans available")
        scan_id = int(latest[0])
        selected_tier = tier
        if selected_tier is None:
            candidates = conn.execute(
                "SELECT DISTINCT tier FROM artifacts WHERE scan_id=? AND status='candidate' AND tier IS NOT NULL",
                (scan_id,),
            ).fetchall()
            selected_tier = max(
                (str(row[0]).lower() for row in candidates if row[0]),
                key=tier_weight,
                default=None,
            )
        if not dry_run:
            _require_tier_confirmation(selected_tier, payload.get("confirmation"))
        staged, moved_bytes = sanitorium.sanitise_moves(
            cfg, conn, scan_id=scan_id, tier=tier, dry_run=dry_run
        )
    except HTTPException:
        conn.close()
        raise
    except (FileExistsError, RuntimeError) as exc:
        conn.close()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        conn.close()
        raise
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
    _check_disk_safety(cfg)
    rel_path = payload.get("path", "")
    if not isinstance(rel_path, str) or not rel_path:
        raise HTTPException(status_code=400, detail="Missing 'path'")
    try:
        sanitorium.quench(cfg, rel_path)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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


def _web_tier(value: Any) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="'tier' must be a tier name")
    tier = value.strip().lower()
    if tier == "11":
        raise HTTPException(status_code=400, detail="Use the named tier 'gigashyte', not '11'")
    tier = {"1": "shyte", "5": "kiloshyte", "10": "megashyte"}.get(tier, tier)
    if tier not in {"shyte", "kiloshyte", "megashyte", "gigashyte"}:
        raise HTTPException(status_code=400, detail=f"Unknown tier: {value}")
    return tier


def _require_tier_confirmation(tier: str | None, supplied: Any) -> None:
    expected = tier_confirmation(tier)
    if expected is None:
        return
    if not isinstance(supplied, str):
        raise HTTPException(status_code=400, detail=f"Type {expected!r} in 'confirmation' to proceed")
    if tier == "gigashyte":
        valid = "".join(ch for ch in supplied.upper() if ch.isalnum()) == "THESEGOTOELEVEN"
    else:
        valid = supplied.strip().upper() == expected
    if not valid:
        raise HTTPException(status_code=400, detail=f"Confirmation did not match {expected!r}")


def _check_disk_safety(cfg: CharkiveConfig) -> None:
    _check_brick_protection(cfg)
    try:
        sanity_runner.gluster_warnings(cfg)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _check_brick_protection(cfg: CharkiveConfig) -> None:
    if forbidden_brick_resolve(cfg.root, cfg.brick):
        raise HTTPException(status_code=403, detail="Brick protection rejected this root")


_CURATION_PROGRESS: dict[str, Any] = {"running": False, "message": ""}


@app.post("/api/curation/run")
async def api_curation_run():
    cfg = _get_config()
    _check_brick_protection(cfg)
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

    token = os.environ.get("CHARKIVE_WEB_TOKEN")
    loopback = _is_loopback_host(host)
    if not loopback and not token:
        raise RuntimeError("Binding Charkive Web beyond localhost requires CHARKIVE_WEB_TOKEN.")

    if config_path:
        global _config
        _config = load_config(Path(config_path))
    uvicorn.run(app, host=host, port=port, log_level="info")
