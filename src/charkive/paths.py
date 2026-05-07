from __future__ import annotations

import os
from pathlib import Path

from charkive.config import BrickCfg, CharkiveConfig


def forbidden_brick_resolve(root: Path, brick_cfg: BrickCfg | None = None) -> bool:
    if brick_cfg and not brick_cfg.enabled:
        return False
    try:
        resolved = root.resolve(strict=False)
    except OSError:
        return True

    forb: tuple[str, ...] = (
        brick_cfg.forbidden_paths
        if brick_cfg
        else (
            "/SANDIEGO",
            "/bricks",
        )
    )

    s = str(resolved)
    # Exact matches and prefix matches against normalized forbidden entries
    norm_list = [_norm_forbid(x) for x in forb]

    if s in frozenset(norm_list):
        return True
    if any(pref and s.startswith(pref) for pref in norm_list):
        return True

    try:
        if (resolved / ".glusterfs").exists():
            return True
        if getattr(os, "listxattr", None):
            xa = os.listxattr(resolved, follow_symlinks=False)
            # Linux returns str attrs; tolerate bytes
            for a in xa:
                name = a if isinstance(a, str) else a.decode("ascii", errors="ignore")
                if name.startswith("trusted.glusterfs"):
                    return True
    except OSError:
        pass
    return False


def _norm_forbid(p: str) -> str:
    p = os.path.abspath(os.path.expanduser(p.rstrip("*").rstrip("/")))
    return p


def jail_check(config: CharkiveConfig, candidate: Path) -> tuple[bool, str]:
    try:
        r = candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        return False, "unresolvable_path"

    if config.sandbox:
        root = config.root.resolve()
        try:
            r.relative_to(root)
            return True, ""
        except ValueError:
            return False, "outside_root"
    return True, ""
