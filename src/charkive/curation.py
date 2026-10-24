"""Document curation: find the user documents worth protecting.

Read-only. Walks the SAN root, scores every user document (notes, office files, PDFs)
for importance and for risk, and groups the results:

  at_risk     important, not versioned in git, not under the sanctuary, so one disk away from gone
  protected   important and already safe (tracked in git, or under the sanctuary)
  duplicates  byte-identical copies (size + first/last 1 MB hash)
  superseded  older drafts/versions with a newer sibling (name_v1 -> name_v2, 'final', 'copy')
  stale       low-value documents untouched for a long time (review candidates, never auto-actioned)

Nothing is moved, renamed or deleted. The only output is a report, plus a suggested
sanctuary snippet the operator can paste into .charkive.yml.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import pathspec

from charkive.config import CharkiveConfig

DOC_EXTS = frozenset({
    ".md", ".txt", ".rst", ".org", ".tex", ".rtf",
    ".doc", ".docx", ".odt", ".pages",
    ".xls", ".xlsx", ".ods", ".numbers",
    ".ppt", ".pptx", ".odp", ".key",
    ".pdf", ".epub",
})

SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".cache", ".npm", ".next", "target", "dist", "build", ".glusterfs", ".trashcan", ".shard",
    ".charkive", ".quarantine", "Media Cache", "Render Files", "CacheClip", "site-packages",
    "Trash", ".Trash", "lost+found",
    # tool and OS litter: boilerplate READMEs/licences here are not the operator's own documents
    ".pytest_cache", ".tox", ".idea", ".vscode", "Program Files", "Program Files (x86)",
    "WINDOWS", "Windows", "Application Data", "Temporary Internet Files", "$RECYCLE.BIN",
    "System Volume Information",
})

# names that are, by convention, the documents a project cannot do without
KEY_NAMES = re.compile(
    r"^(readme|agents|claude|chronicle|infra|architecture|design|roadmap|todo|notes|"
    r"handover|handoff|runbook|spec|plan|decisions?)\b", re.I)
VERSIONED = re.compile(r"[_\- .]v(\d+)$|[_\- ]\((\d+)\)$|[_\- ](copy|old|backup|draft|final)$", re.I)
VOLATILE_PARTS = frozenset({"tmp", "temp", "cache", "caches", "backup", "backups", "old", "trash", "downloads"})

MAX_FILES = 1_500_000      # hard ceiling per run
TIME_BUDGET_S = 2400       # and a wall-clock ceiling (the SAN walk is slow)
STALE_DAYS = 730
IMPORTANT_AT = 40


def _partial_hash(path: Path) -> str | None:
    try:
        size = path.stat().st_size
        h = hashlib.sha1()
        with open(path, "rb") as f:
            h.update(f.read(1_048_576))
            if size > 2_097_152:
                f.seek(-1_048_576, 2)
                h.update(f.read(1_048_576))
        return h.hexdigest()
    except OSError:
        return None


class _Repos:
    """Lazily maps a directory to its git repo root and that repo's set of tracked files."""

    def __init__(self) -> None:
        self._root_of: dict[str, str | None] = {}
        self._tracked: dict[str, frozenset[str]] = {}

    def root(self, d: Path, stop: Path) -> Path | None:
        key = str(d)
        if key in self._root_of:
            r = self._root_of[key]
            return Path(r) if r else None
        found: Path | None = None
        p = d
        while True:
            if (p / ".git").exists():
                found = p
                break
            if p == stop or p.parent == p:
                break
            p = p.parent
        self._root_of[key] = str(found) if found else None
        return found

    def is_tracked(self, repo: Path, path: Path) -> bool:
        k = str(repo)
        if k not in self._tracked:
            try:
                out = subprocess.run(
                    ["git", "-c", "safe.directory=*", "-C", k, "ls-files", "-z"],
                    capture_output=True, timeout=30, check=True).stdout
                self._tracked[k] = frozenset(
                    x.decode("utf-8", "surrogateescape") for x in out.split(b"\0") if x)
            except (OSError, subprocess.SubprocessError):
                self._tracked[k] = frozenset()
        try:
            return str(path.relative_to(repo)) in self._tracked[k]
        except ValueError:
            return False


def _score(path: Path, rel: str, st: os.stat_result, tracked: bool, in_repo: bool,
           sanctuary: bool, now: float) -> tuple[int, list[str]]:
    score, why = 0, []
    ext = path.suffix.lower()
    if ext in {".docx", ".doc", ".odt", ".pdf", ".xlsx", ".xls", ".ods", ".pptx", ".pages", ".numbers", ".key", ".md"}:
        score += 20
        why.append("authored document type")
    elif ext in {".txt", ".rst", ".org", ".tex", ".rtf"}:
        score += 10
    if KEY_NAMES.match(path.stem):
        score += 30
        why.append("key project document (" + path.stem + ")")
    age_days = (now - st.st_mtime) / 86400
    if age_days <= 180:
        score += 15
        why.append("edited in the last 6 months")
    elif age_days <= 730:
        score += 5
    if st.st_size >= 50_000:
        score += 10
        why.append("substantial (%d KB)" % (st.st_size // 1024))
    elif st.st_size < 300:
        score -= 20
        why.append("nearly empty")
    parts = {x.lower() for x in Path(rel).parts[:-1]}
    if parts & VOLATILE_PARTS:
        score -= 25
        why.append("lives in a temp/backup/downloads folder")
    if VERSIONED.search(path.stem):
        score -= 10
    if sanctuary:
        why.append("under the sanctuary")
    elif tracked:
        why.append("versioned in git")
    elif in_repo:
        why.append("inside a git repo but NOT tracked")
    else:
        why.append("not under version control")
    return max(score, 0), why


def run(cfg: CharkiveConfig, progress: Callable[[str], None] = lambda m: None) -> dict[str, Any]:
    root = cfg.root.resolve()
    sanct = pathspec.PathSpec.from_lines("gitwildmatch", list(cfg.sanctuary))
    repos = _Repos()
    now = time.time()
    deadline = now + TIME_BUDGET_S
    docs: list[dict[str, Any]] = []
    seen = 0
    truncated = False

    last_note = 0.0
    stack = [root]
    while stack:
        d = stack.pop()
        if seen >= MAX_FILES or time.time() > deadline:
            truncated = True
            break
        try:
            it = list(os.scandir(d))
        except OSError:
            continue
        for e in it:
            try:
                if e.is_symlink():
                    continue
                if e.is_dir(follow_symlinks=False):
                    if e.name not in SKIP_DIRS:
                        stack.append(Path(e.path))
                    continue
                if not e.is_file(follow_symlinks=False):
                    continue
            except OSError:
                continue
            seen += 1
            p = Path(e.path)
            if p.suffix.lower() not in DOC_EXTS:
                continue
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            rel = str(p.relative_to(root))
            repo = repos.root(p.parent, root)
            tracked = bool(repo and repos.is_tracked(repo, p))
            in_sanct = sanct.match_file(rel)
            score, why = _score(p, rel, st, tracked, repo is not None, in_sanct, now)
            docs.append({
                "path": rel, "size": st.st_size, "mtime": int(st.st_mtime), "score": score,
                "tracked": tracked, "in_repo": repo is not None, "sanctuary": in_sanct, "why": why,
            })
        if time.time() - last_note > 5:
            last_note = time.time()
            progress("Walking: %d files seen, %d documents, %d folders queued" % (seen, len(docs), len(stack)))

    progress("Hashing for duplicates (%d documents)" % len(docs))
    by_size: dict[int, list[dict]] = defaultdict(list)
    for x in docs:
        if x["size"] >= 300:
            by_size[x["size"]].append(x)
    dup_groups = []
    for group in by_size.values():
        if len(group) < 2:
            continue
        by_hash: dict[str, list[dict]] = defaultdict(list)
        for x in group:
            h = _partial_hash(root / x["path"])
            if h:
                by_hash[h].append(x)
        for h, same in by_hash.items():
            if len(same) > 1:
                # keep suggestion: tracked/sanctuary first, then newest
                same.sort(key=lambda z: (bool({q.lower() for q in Path(z["path"]).parts[:-1]} & VOLATILE_PARTS),
                                         not (z["tracked"] or z["sanctuary"]), -z["mtime"]))
                dup_groups.append({"size": same[0]["size"], "keep": same[0]["path"],
                                   "copies": [z["path"] for z in same]})
                for z in same[1:]:
                    z["duplicate_of"] = same[0]["path"]
    dup_groups.sort(key=lambda g: g["size"] * (len(g["copies"]) - 1), reverse=True)

    # superseded: same directory, same base name, a higher version/'final' exists
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for x in docs:
        p = Path(x["path"])
        base = VERSIONED.sub("", p.stem).lower()
        groups[(str(p.parent), base, p.suffix.lower())].append(x)
    superseded = []
    for items in groups.values():
        if len(items) < 2:
            continue
        items.sort(key=lambda z: z["mtime"], reverse=True)
        newest = items[0]
        for old in items[1:]:
            if old["mtime"] < newest["mtime"] and old["path"] != newest["path"]:
                old["superseded_by"] = newest["path"]
                superseded.append({"path": old["path"], "superseded_by": newest["path"], "size": old["size"]})

    def view(x: dict) -> dict:
        return {k: x[k] for k in ("path", "size", "mtime", "score", "tracked", "sanctuary", "why")}

    important = [x for x in docs if x["score"] >= IMPORTANT_AT]
    at_risk = sorted((x for x in important if not x["tracked"] and not x["sanctuary"]
                      and "duplicate_of" not in x), key=lambda z: -z["score"])
    protected = sorted((x for x in important if x["tracked"] or x["sanctuary"]), key=lambda z: -z["score"])
    stale = sorted((x for x in docs if x["score"] < 25 and now - x["mtime"] > STALE_DAYS * 86400
                    and not x["tracked"] and not x["sanctuary"]), key=lambda z: -z["size"])

    # suggest sanctuary globs: the project folders holding the most at-risk documents
    per_dir: dict[str, int] = defaultdict(int)
    for x in at_risk:
        parts = Path(x["path"]).parts
        per_dir["/".join(parts[:2]) if len(parts) > 2 else "/".join(parts[:-1])] += 1
    suggested = ["/%s/**" % d for d, _ in sorted(per_dir.items(), key=lambda kv: -kv[1])[:15] if d]

    report = {
        "generated": int(now),
        "root": str(root),
        "files_seen": seen,
        "truncated": truncated,
        "documents": len(docs),
        "counts": {"at_risk": len(at_risk), "protected": len(protected), "duplicate_groups": len(dup_groups),
                   "superseded": len(superseded), "stale": len(stale)},
        "at_risk": [view(x) for x in at_risk[:300]],
        "protected": [view(x) for x in protected[:100]],
        "duplicates": dup_groups[:150],
        "superseded": superseded[:300],
        "stale": [view(x) for x in stale[:200]],
        "suggested_sanctuary": suggested,
    }
    progress("Done: %d documents, %d at risk" % (len(docs), len(at_risk)))
    return report


def save(cfg: CharkiveConfig, report: dict[str, Any]) -> Path:
    out = cfg.sanitorium_absolute().parent / "curation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(report))
    tmp.replace(out)
    return out


def load(cfg: CharkiveConfig) -> dict[str, Any] | None:
    p = cfg.sanitorium_absolute().parent / "curation.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None
