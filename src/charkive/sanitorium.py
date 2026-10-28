from __future__ import annotations

import errno
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from charkive import db
from charkive.config import CharkiveConfig
from charkive.paths import forbidden_brick_resolve


def _iso_week_dir() -> str:
    iso = datetime.now(UTC).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _manifest_path(bucket: Path) -> Path:
    return bucket / "manifest.ndjson"


def _move_no_replace(src: Path, dest: Path) -> None:
    """Move a regular file without ever replacing an existing destination."""
    try:
        os.link(src, dest, follow_symlinks=False)
    except OSError as exc:
        if exc.errno not in {errno.EXDEV, errno.EPERM, errno.EOPNOTSUPP, errno.ENOTSUP}:
            raise

        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as target, src.open("rb") as source:
                shutil.copyfileobj(source, target)
                target.flush()
                os.fsync(target.fileno())
            shutil.copystat(src, dest, follow_symlinks=False)
        except Exception:
            dest.unlink(missing_ok=True)
            raise

    src.unlink()


def _safe_relative_path(value: str) -> Path:
    rel = PurePosixPath(value)
    if rel.is_absolute() or not rel.parts or any(part in {"", ".", ".."} for part in rel.parts):
        raise RuntimeError(f"Unsafe relative path in Charkive state: {value!r}")
    return Path(*rel.parts)


def sanitise_moves(
    cfg: CharkiveConfig,
    conn,
    *,
    scan_id: int,
    tier: str | None,
    dry_run: bool,
) -> tuple[list[int], int]:
    if forbidden_brick_resolve(cfg.root, cfg.brick):
        raise RuntimeError("Brick protection rejected this root; mount the Gluster export instead.")

    root = cfg.root.resolve()
    san_root = cfg.sanitorium_absolute()
    bucket = san_root / _iso_week_dir()
    if cfg.sandbox:
        try:
            bucket.relative_to(root)
            san_root.relative_to(root)
        except ValueError as exc:
            raise RuntimeError(f"SANitorium escapes configured root ({exc}). Aborting.") from exc

    tier_key = tier.lower() if tier else None
    rows = db.candidates(conn, scan_id, tier_filter=tier_key)

    pending: list[tuple[int, Path, Path, int]] = []
    for aid, rel_posix, nbytes in rows:
        rel_path = _safe_relative_path(rel_posix)
        src = root / rel_path
        if not src.exists() or not src.is_file():
            continue
        if src.is_symlink():
            raise RuntimeError(f"Refusing to move symlink: {src}")
        try:
            src.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Candidate escapes configured root: {src}") from exc

        dest = bucket / rel_path
        try:
            dest.parent.resolve(strict=False).relative_to(san_root)
        except ValueError as exc:
            raise RuntimeError(f"SANitorium destination escapes configured path: {dest}") from exc
        if os.path.lexists(dest):
            raise FileExistsError(f"SANitorium destination already exists; refusing to overwrite: {dest}")
        pending.append((aid, src, dest, int(nbytes)))

    if not dry_run:
        san_root.mkdir(parents=True, exist_ok=True)

    staged: list[int] = []
    moved_bytes = 0
    manifest_records: list[dict[str, object]] = []

    for aid, src, dest, nbytes in pending:

        manifest_records.append(
            {
                "artifact_id": aid,
                "from": src.relative_to(root).as_posix(),
                "to": dest.relative_to(san_root).as_posix(),
                "tier": tier_key,
                "bytes": nbytes,
                "dry_run": dry_run,
                "utc": datetime.now(UTC).isoformat(timespec="seconds"),
            }
        )

        if dry_run:
            staged.append(aid)
            moved_bytes += nbytes
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.parent.resolve(strict=True).relative_to(san_root)
        except ValueError as exc:
            raise RuntimeError(f"SANitorium destination escapes configured path: {dest}") from exc
        _move_no_replace(src, dest)

        staged.append(aid)
        moved_bytes += nbytes

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
    if forbidden_brick_resolve(cfg.root, cfg.brick):
        raise RuntimeError("Brick protection rejected this root; mount the Gluster export instead.")

    san_root = cfg.sanitorium_absolute().resolve()
    rel_path = _safe_relative_path(sanitor_relative)
    source = san_root / rel_path
    if source.is_symlink():
        raise RuntimeError("Refusing to restore a symlink from SANitorium.")
    rescued = source.resolve(strict=True)
    try:
        under = rescued.relative_to(san_root)
    except ValueError as exc:
        raise RuntimeError("Quench target is outside SANitorium.") from exc
    if not rescued.is_file():
        raise RuntimeError("Quench target is not a regular file.")
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
    if os.path.lexists(dst):
        raise FileExistsError(f"Restore destination already exists; refusing to overwrite: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        dst.parent.resolve(strict=True).relative_to(root_norm)
    except ValueError as exc:
        raise RuntimeError("Refusing to restore through a path outside configured root.") from exc
    _move_no_replace(rescued, dst)
