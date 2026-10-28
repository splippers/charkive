from __future__ import annotations

import os
from pathlib import Path

from charkive.config import BrickCfg, CharkiveConfig


def forbidden_brick_resolve(root: Path, brick_cfg: BrickCfg | None = None) -> bool:
    if brick_cfg and not brick_cfg.enabled:
        return False
    try:
        resolved = root.resolve(strict=False)
    except (OSError, RuntimeError):
        return True

    forb: tuple[str, ...] = brick_cfg.forbidden_paths if brick_cfg else ()

    s = str(resolved)
    # Exact matches and prefix matches against normalized forbidden entries
    norm_list = [_norm_forbid(x) for x in forb if x.strip()]

    if s in frozenset(norm_list):
        return True
    if any(pref and s.startswith(pref.rstrip(os.sep) + os.sep) for pref in norm_list):
        return True

    for probe in (resolved, *resolved.parents):
        try:
            if (probe / ".glusterfs").exists():
                return True
            if getattr(os, "listxattr", None):
                xa = os.listxattr(probe, follow_symlinks=False)
                for a in xa:
                    name = a if isinstance(a, str) else a.decode("ascii", errors="ignore")
                    if name.startswith("trusted.glusterfs"):
                        return True
        except OSError:
            continue
    return False


def _norm_forbid(p: str) -> str:
    expanded = os.path.expanduser(p.rstrip("*"))
    if expanded != os.path.sep:
        expanded = expanded.rstrip(os.path.sep)
    return os.path.abspath(expanded)


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
