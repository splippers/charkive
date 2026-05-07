from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import pathspec


TIER_WEIGHT: dict[str, int] = {
    "shyte": 1,
    "kiloshyte": 5,
    "megashyte": 10,
    "gigashyte": 11,
}


def tier_weight(name: str | None) -> int:
    if not name:
        return 0
    return TIER_WEIGHT.get(name.lower(), 0)


def _pat_for_gitwild(rel_pat: str) -> str:
    p = rel_pat.strip().replace("\\", "/").lstrip(".")
    while p.startswith("/"):
        p = p[1:]
    return p


def _immutable(path: Path) -> bool:
    getxa = getattr(os, "getxattr", None)
    if not getxa:
        return False
    attrs = ["user.immutable", b"user.immutable"]
    for cand in attrs:
        try:
            v = getxa(path, cand, follow_symlinks=False)
            if v in (False, None):
                continue
            if isinstance(v, bytes):
                if v.strip() == b"" or v.strip().lower() in {b"0", b"false", b"no"}:
                    continue
            elif str(v).strip().lower() in {"", "0", "false", "no"}:
                continue
            return True
        except OSError:
            continue
    return False


def _mtime_age_days(st: os.stat_result, now: float) -> float:
    try:
        return max(0.0, (now - float(st.st_mtime)) / 86400.0)
    except OverflowError:
        return 0.0


def _atime_age_days(st: os.stat_result, now: float) -> float | None:
    try:
        return max(0.0, (now - float(st.st_atime)) / 86400.0)
    except OverflowError:
        return None


@dataclass
class CompiledRule:
    raw: dict[str, Any]
    name: str
    tier: str
    path_spec: pathspec.PathSpec | None
    basename_lower: tuple[str, ...]


class FireCodes:
    def __init__(
        self,
        sanctuary_patterns: tuple[str, ...],
        sanity_rules: tuple[dict[str, Any], ...],
        protect_extensions: frozenset[str],
        *,
        protect_path_markers: tuple[str, ...] = (
            "/archive/",
            "/masters/",
            "/originals/",
            "/deliverables/",
            "/delivery/",
            "/final/",
            "/camera/",
            "/ingest/",
        ),
    ):
        s_lines = [_pat_for_gitwild(p) for p in sanctuary_patterns if str(p).strip()]
        self._sanctuary = pathspec.PathSpec.from_lines("gitwildmatch", s_lines) if s_lines else None
        self._protect_extensions = frozenset(x.lower() for x in protect_extensions)
        self._protect_markers = tuple(m.lower().strip("/") for m in protect_path_markers)
        self.rules: list[CompiledRule] = []

        for r in sanity_rules:
            name = str(r.get("name", "rule"))
            tier_s = _tier_str(r.get("tier") or r.get("Tier"))
            if not tier_s:
                continue
            pat_raw = str(r.get("path") or r.get("glob") or r.get("match_path") or "").strip()
            path_spec = None
            if pat_raw:
                path_spec = pathspec.PathSpec.from_lines("gitwildmatch", [_pat_for_gitwild(pat_raw)])
            raw_mt = (
                r.get("match") or r.get("match_names") or r.get("basename") or ()
            )
            if isinstance(raw_mt, str):
                mseq: tuple[Any, ...] = (raw_mt,)
            else:
                try:
                    mseq = tuple(raw_mt or ())
                except TypeError:
                    mseq = ()
            basename_lower = tuple(str(x).lower() for x in mseq)
            raw_ext = r.get("extensions") or r.get("ext")
            if isinstance(raw_ext, str):
                ext_seq: tuple[Any, ...] = (raw_ext,)
            else:
                try:
                    ext_seq = tuple(raw_ext or ())
                except TypeError:
                    ext_seq = ()
            if not pat_raw and not basename_lower and not ext_seq:
                continue

            self.rules.append(
                CompiledRule(
                    raw=r,
                    name=name,
                    tier=tier_s,
                    path_spec=path_spec,
                    basename_lower=basename_lower,
                )
            )

        self.rules.sort(key=lambda cr: tier_weight(cr.tier), reverse=True)

    def classify(
        self,
        full_path: Path,
        rel_posix: str,
        *,
        st: os.stat_result,
        now: float | None = None,
    ) -> tuple[str, str | None, str | None]:
        """Return status in {protect,candidate,review}, optional tier name, matched rule."""
        now_t = now if now is not None else time.time()
        rel_adj = PurePosixPath(rel_posix).as_posix()
        prefix = "/" + rel_adj.lower() + "/"

        if _immutable(full_path):
            return "protect", None, None

        if self._sanctuary is not None and self._sanctuary.match_file(rel_adj):
            return "protect", None, None

        matched_marker = False
        for marker in self._protect_markers:
            needle = "/" + marker + "/"
            if needle in prefix or rel_adj.lower().startswith(marker + "/"):
                matched_marker = True
                suf = PurePosixPath(rel_posix).suffix.lower()
                if suf in self._protect_extensions:
                    return "protect", None, None

        ext = PurePosixPath(rel_posix).suffix.lower()
        if not matched_marker and ext in self._protect_extensions:
            return "protect", None, None

        matches: list[tuple[int, str, str]] = []
        for cr in self.rules:
            if cr.basename_lower:
                bn = PurePosixPath(rel_posix).name.lower()
                if bn not in cr.basename_lower:
                    continue

            if cr.path_spec is not None and not cr.path_spec.match_file(rel_adj):
                continue

            if not rule_extensions_matches(cr.raw, ext):
                continue

            if not sibling_requirements_met(full_path, cr.raw):
                continue

            if not age_checks_ok(cr.raw, st, now_t):
                continue

            if not size_checks_ok(cr.raw, st.st_size):
                continue

            tw = tier_weight(cr.tier)
            matches.append((tw, cr.tier, cr.name))

        if matches:
            _w, best_tier, best_rule = max(matches, key=lambda m: (m[0], m[1]))
            return "candidate", best_tier, best_rule
        return "review", None, None


def _tier_str(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    t = raw.strip().lower()
    return t if t in TIER_WEIGHT else None


def rule_extensions_matches(rule: dict[str, Any], ext_l: str) -> bool:
    raw_exts = rule.get("extensions") or rule.get("ext") or ()
    if not raw_exts:
        return True
    want = {_norm_ext_tuple(x) for x in raw_exts}
    return ext_l in want


def _norm_ext_tuple(x: Any) -> str:
    s = str(x).strip().lower().lstrip(".")
    return f".{s}" if s else ""


def sibling_requirements_met(full_path: Path, rule: dict[str, Any]) -> bool:
    need = rule.get("require_no_sibling") or rule.get("missing_siblings") or ()
    if not need:
        return True
    for x in need:
        ext = _norm_ext_tuple(x)
        if not ext:
            continue
        cand = full_path.with_suffix(ext)
        if cand.exists():
            return False
    return True


def age_checks_ok(rule: dict[str, Any], st: os.stat_result, now: float) -> bool:
    if "age_days" in rule:
        need = float(rule["age_days"])
        if need > 0 and _mtime_age_days(st, now) < need:
            return False

    if "mtime_days" in rule:
        need = float(rule["mtime_days"])
        if need > 0 and _mtime_age_days(st, now) < need:
            return False

    if "atime_days" in rule:
        need = float(rule["atime_days"])
        ad = _atime_age_days(st, now)
        if ad is None or ad < need:
            return False
    return True


def size_checks_ok(rule: dict[str, Any], size_bytes: int) -> bool:
    if "min_size" in rule:
        ms = rule["min_size"]
        thresh = parse_size(ms)
        if size_bytes < thresh:
            return False

    mx = rule.get("max_size_bytes") or rule.get("max_size")
    if mx is None:
        return True

    thresh = parse_size(mx) if not isinstance(mx, (int, float)) else int(mx)
    return size_bytes <= thresh


def parse_size(spec: Any) -> int:
    if isinstance(spec, (int, float)):
        return int(spec)
    s = str(spec).strip().lower()
    mul = 1
    if s.endswith("gb"):
        mul = 1024**3
        s = s[:-2].strip()
    elif s.endswith("mb"):
        mul = 1024**2
        s = s[:-2].strip()
    elif s.endswith("kb"):
        mul = 1024
        s = s[:-2].strip()

    parts = s.split(".", 1)
    if parts[0] == "":
        return 0
    whole = parts[0]
    frac = parts[1] if len(parts) > 1 else "0"

    base = float(whole + "." + frac)
    return int(base * mul)
