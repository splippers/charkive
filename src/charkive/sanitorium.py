from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from charkive import db
from charkive.config import CharkiveConfig


def _iso_week_dir() -> str:
    iso = datetime.now(UTC).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _manifest_path(bucket: Path) -> Path:
    return bucket / "manifest.ndjson"


def sanitise_moves(
    cfg: CharkiveConfig,
    conn,
    *,
    scan_id: int,
    tier: str | None,
    dry_run: bool,
) -> tuple[list[int], int]:
    root = cfg.root.resolve()
    san_root = cfg.sanitorium_absolute()
    bucket = san_root / _iso_week_dir()
    if not cfg.sandbox:
        pass
    else:
        try:
            bucket.relative_to(root)
            san_root.relative_to(root)
        except ValueError as exc:
            raise RuntimeError(f"SANitorium escapes configured root ({exc}). Aborting.") from exc

    san_root.mkdir(parents=True, exist_ok=True)
    tier_key = tier.lower() if tier else None
    rows = db.candidates(conn, scan_id, tier_filter=tier_key)

    staged: list[int] = []
    moved_bytes = 0
    manifest_records: list[dict[str, object]] = []

    for aid, rel_posix, nbytes in rows:
        src = root / rel_posix
        if not src.exists() or not src.is_file():
            continue

        dest = bucket / rel_posix

        manifest_records.append(
            {
                "artifact_id": aid,
                "from": rel_posix,
                "to": dest.relative_to(san_root).as_posix(),
                "tier": tier_key,
                "bytes": nbytes,
                "dry_run": dry_run,
                "utc": datetime.now(UTC).isoformat(timespec="seconds"),
            }
        )

        if dry_run:
            staged.append(aid)
            moved_bytes += int(nbytes)
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp_dest = Path(str(dest) + ".charkiving")
        shutil.move(str(src), str(tmp_dest))
        tmp_dest.replace(dest)

        staged.append(aid)
        moved_bytes += int(nbytes)

    if manifest_records and not dry_run:
        mf = _manifest_path(bucket)
        mf.parent.mkdir(parents=True, exist_ok=True)
        lines = "".join(json.dumps(rec, separators=(",", ":")) + "\n" for rec in manifest_records)
        with mf.open("a", encoding="utf-8") as fh:
            fh.write(lines)

    if not dry_run and staged:
        db.mark_quarantined(conn, ids=staged)

    return staged, moved_bytes


def list_contents(cfg: CharkiveConfig, *, depth: int = 2, limit_dirs: int = 50) -> list[str]:
    root = cfg.sanitorium_absolute()
    if not root.exists():
        return [f"No SANitorium yet at {root}"]
    out: list[str] = []

    dirs = sorted([p for p in root.iterdir() if p.is_dir()])[:limit_dirs]
    out.append(str(root.resolve()))
    for d in dirs:
        out.append(str(d.relative_to(root)))
        if depth <= 1:
            continue
        subdirs = sorted([p for p in d.iterdir() if p.is_dir()])[:20]
        for sd in subdirs:
            out.append(str(sd.relative_to(root)))
    return out


def purge_note() -> str:
    return "SANitorium retention purge is cron/workflow territory — automated purge CLI not wired yet."


def quench(cfg: CharkiveConfig, sanitor_relative: str) -> None:
    san_root = cfg.sanitorium_absolute().resolve()
    rel = sanitor_relative.lstrip("/.")
    rescued = (san_root / rel).resolve()
    try:
        under = rescued.relative_to(san_root)
    except ValueError as exc:
        raise RuntimeError("Quench target is outside SANitorium.") from exc
    parts = under.parts
    if len(parts) < 2:
        raise RuntimeError("Expected YEAR-W-xx/relative/path...")
    root_norm = cfg.root.resolve()
    rest = Path(*parts[1:])
    dst = (root_norm / rest).resolve()
    try:
        dst.relative_to(root_norm)
    except ValueError as exc:
        raise RuntimeError("Refusing to restore outside configured root.") from exc
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(dst) + ".charkiving")
    shutil.move(str(rescued), str(tmp))
    tmp.replace(dst)
