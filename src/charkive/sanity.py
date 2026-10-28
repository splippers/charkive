from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from charkive import db
from charkive.config import CharkiveConfig
from charkive.fire_codes import FireCodes
from charkive.paths import jail_check


def partial_hash(path: Path, *, chunk: int = 1_048_576) -> str:
    h = hashlib.sha1()
    size = path.stat().st_size
    with path.open("rb") as fh:
        h.update(fh.read(chunk))
        if size > chunk * 2:
            fh.seek(-chunk, os.SEEK_END)
            h.update(fh.read(chunk))
    return h.hexdigest()


class SkipStats:
    def __init__(self) -> None:
        self.symlink = 0
        self.outside_root = 0
        self.unreadable_dir = 0


def gluster_warnings(cfg: CharkiveConfig) -> list[str]:
    vol = cfg.gluster.volume
    if not vol:
        return []
    if shutil.which("gluster") is None:
        raise RuntimeError("Gluster CLI not installed; refusing to skip configured Gluster safety checks.")

    try:
        heal = subprocess.run(
            ["gluster", "volume", "heal", vol, "info"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Gluster heal probe failed: {exc}") from exc

    if heal.returncode != 0:
        raise RuntimeError(f"Gluster heal probe failed: {heal.stderr.strip() or heal.stdout.strip()}")
    heals = [int(x) for x in re.findall(r"^\s*Number of entries:\s*(\d+)\s*$", heal.stdout, flags=re.I | re.M)]
    if not heals:
        raise RuntimeError("Gluster heal output was unrecognized; refusing to proceed.")
    if any(count > 0 for count in heals):
        raise RuntimeError(
            "Gluster heal entries remain on this volume. Fix heals before sanitising SAN data."
        )

    try:
        status = subprocess.run(
            ["gluster", "volume", "status", vol],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Gluster status probe failed: {exc}") from exc

    if status.returncode != 0:
        raise RuntimeError(f"Gluster status probe failed: {status.stderr.strip() or status.stdout.strip()}")
    bricks = re.findall(r"^\s*Brick\s*:\s*.+$", status.stdout, flags=re.I | re.M)
    online = re.findall(r"^\s*Online:\s*(\S+)\s*$", status.stdout, flags=re.I | re.M)
    if not bricks or len(bricks) != len(online) or any(value.upper() != "Y" for value in online):
        raise RuntimeError("Gluster status output was unhealthy or unrecognized; inspect `gluster volume status`.")

    return []


def run_scan(cfg: CharkiveConfig, *, do_hash: bool = False, progress_every: int = 2500) -> tuple[int, SkipStats]:
    root = cfg.root.resolve()
    conn = db.connect(cfg.state_db_path())
    scan_id = db.start_scan(conn, root)

    fc = FireCodes(cfg.sanctuary, cfg.sanity_rules, cfg.protect_extensions)
    stats = SkipStats()
    batch: list[tuple[str, int, float, str, str | None, str | None, str | None]] = []

    scanned = 0
    stack: list[Path] = [root]
    root_norm = root.resolve(strict=False)

    while stack:
        here = stack.pop()

        rp: tuple[str, ...] = ()
        try:
            rp = tuple(here.relative_to(root_norm).parts)
        except ValueError:
            continue
        if rp and rp[0] == ".charkive":
            continue
        if any(p == ".charkive" for p in rp):
            continue

        try:
            children = sorted(here.iterdir(), key=lambda x: x.name, reverse=False)
        except OSError:
            stats.unreadable_dir += 1
            continue

        for p in reversed(children):
            try:
                if p.name == ".git" or p.name == ".charkive.yml" or ".Trash" in p.name:
                    continue
                if p.is_symlink():
                    stats.symlink += 1
                    continue
                if p.is_dir():
                    stack.append(p)
                    continue
                if not p.is_file():
                    continue

                okay, _reason = jail_check(cfg, p)
                if cfg.sandbox and not okay:
                    stats.outside_root += 1
                    continue

                rp_file = ()
                try:
                    rp_file = tuple(p.relative_to(root_norm).parts)
                except ValueError:
                    stats.outside_root += 1
                    continue
                if rp_file and rp_file[0] == ".charkive":
                    continue

                st = p.stat()
                rel_posix = Path(*rp_file).as_posix() if rp_file else p.name

                ph: str | None = None
                if do_hash and st.st_size > 0:
                    try:
                        ph = partial_hash(p)
                    except OSError:
                        ph = None

                status, tier, rn = fc.classify(p, rel_posix, st=st, now=time.time())
                batch.append((rel_posix, int(st.st_size), float(st.st_mtime), status, tier, rn, ph))
                scanned += 1

                if len(batch) >= progress_every:
                    db.bulk_upsert_artifacts(conn, scan_id=scan_id, batch=batch)
                    conn.commit()
                    batch.clear()

            except OSError:
                stats.unreadable_dir += 1

    if batch:
        db.bulk_upsert_artifacts(conn, scan_id=scan_id, batch=batch)
        conn.commit()

    db.finish_scan(conn, scan_id, scanned)
    conn.close()
    return scan_id, stats


def summarize_for_tier(summary: dict, tier: str | None) -> dict:
    if not tier:
        return summary
    t = tier.strip().lower()
    out = dict(summary)
    out["by_tier"] = {k: v for k, v in summary["by_tier"].items() if str(k).lower() == t}
    tier_info = summary["by_tier"].get(t)
    fluff_b = int((tier_info or {}).get("bytes", 0))
    fluff_f = int((tier_info or {}).get("files", 0))
    out["fluff"] = {"bytes": fluff_b, "files": fluff_f}
    return out
