from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from charkive.config import CharkiveConfig

VALID_STATUSES = frozenset({
    "active", "parked", "archived", "stub", "prototype", "concept", "blocked", "joke", "unknown",
})

STATUS_ORDER: dict[str, int] = {
    "active": 0,
    "parked": 1,
    "prototype": 2,
    "concept": 3,
    "blocked": 4,
    "stub": 5,
    "joke": 6,
    "archived": 7,
    "unknown": 8,
}


@dataclass
class ProjectInfo:
    path: Path
    name: str
    status: str
    note: str
    tagged_at: str | None
    last_modified: float
    file_count: int
    total_size: int
    has_git: bool
    has_readme: bool
    has_src: bool
    subdirs: list[str] = field(default_factory=list)


def read_project_status(project_dir: Path) -> dict[str, Any] | None:
    ps_file = project_dir / ".project-status"
    if not ps_file.is_file():
        return None
    with ps_file.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        return None
    return raw


def write_project_status(project_dir: Path, status: str, note: str = "") -> None:
    data = {
        "status": status,
        "note": note,
        "tagged_at": time.strftime("%Y-%m-%d"),
    }
    ps_file = project_dir / ".project-status"
    with ps_file.open("w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False)


def classify_by_heuristics(project_dir: Path) -> str:
    if not project_dir.is_dir():
        return "unknown"

    has_git = (project_dir / ".git").is_dir()
    has_src_dir = (project_dir / "src").is_dir()
    py_files = list(project_dir.glob("*.py"))
    js_files = list(project_dir.glob("*.js"))
    has_code = has_src_dir or bool(py_files) or bool(js_files)
    has_readme = bool(list(project_dir.glob("[Rr][Ee][Aa][Dd][Mm][Ee]*")))

    try:
        latest = max(
            (p.stat().st_mtime for p in project_dir.rglob("*") if p.is_file()),
            default=0.0,
        )
    except OSError:
        latest = 0.0
    now = time.time()
    age_days = (now - latest) / 86400.0 if latest else 9999.0

    try:
        file_count = sum(1 for _ in project_dir.rglob("*") if _.is_file())
    except OSError:
        file_count = 0

    if file_count == 0:
        return "stub"
    if file_count < 5 and not has_git and not has_code:
        return "stub"

    if age_days > 730 and not has_git:
        return "archived"

    if age_days > 365 and not has_code:
        return "parked"

    if has_code or has_git:
        if age_days < 90:
            return "active"
        return "parked"

    if has_readme and file_count < 20:
        return "prototype"

    if file_count < 10:
        return "stub"

    return "unknown"


def get_project_info(project_dir: Path) -> ProjectInfo | None:
    if not project_dir.is_dir():
        return None
    if project_dir.name.startswith("."):
        return None

    ps_data = read_project_status(project_dir)

    if ps_data:
        raw_status = str(ps_data.get("status", "unknown")).strip().lower()
        status = raw_status if raw_status in VALID_STATUSES else "unknown"
        note = str(ps_data.get("note", ""))
        tagged_at = str(ps_data.get("tagged_at", "")) if ps_data.get("tagged_at") else None
    else:
        status = classify_by_heuristics(project_dir)
        note = ""
        tagged_at = None

    try:
        all_files = list(project_dir.rglob("*"))
        file_count = sum(1 for p in all_files if p.is_file())
        total_size = sum(p.stat().st_size for p in all_files if p.is_file())
        last_modified = max(
            (p.stat().st_mtime for p in all_files if p.is_file()),
            default=0.0,
        )
    except OSError:
        file_count = 0
        total_size = 0
        last_modified = 0.0

    has_git = (project_dir / ".git").is_dir()
    has_readme = bool(list(project_dir.glob("[Rr][Ee][Aa][Dd][Mm][Ee]*")))
    has_src = (project_dir / "src").is_dir() or bool(list(project_dir.glob("*.py")))

    subdirs = sorted([
        p.name for p in project_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    ])

    return ProjectInfo(
        path=project_dir,
        name=project_dir.name,
        status=status,
        note=note,
        tagged_at=tagged_at,
        last_modified=last_modified,
        file_count=file_count,
        total_size=total_size,
        has_git=has_git,
        has_readme=has_readme,
        has_src=has_src,
        subdirs=subdirs,
    )


def scan_projects(root_dir: Path) -> list[ProjectInfo]:
    projects: list[ProjectInfo] = []
    if not root_dir.is_dir():
        return projects
    for child in sorted(root_dir.iterdir()):
        info = get_project_info(child)
        if info is not None:
            projects.append(info)
    projects.sort(key=lambda p: (STATUS_ORDER.get(p.status, 99), p.name))
    return projects


def fmt_bytes(nbytes: float | int) -> str:
    n = float(nbytes)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024.0 or unit == "PB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.2f} {unit}"
        n /= 1024.0


def render_project_report(projects: list[ProjectInfo], root: Path) -> str:
    lines = [
        f"Charkive Project Scan — {root.resolve()}",
        f"Total projects: {len(projects)}",
        "",
    ]

    by_status: dict[str, list[ProjectInfo]] = {}
    for p in projects:
        by_status.setdefault(p.status, []).append(p)

    for status in ("active", "parked", "prototype", "concept", "blocked", "stub", "joke", "archived", "unknown"):
        batch = by_status.pop(status, None)
        if batch is None:
            continue
        total_files = sum(p.file_count for p in batch)
        total_size = sum(p.total_size for p in batch)
        lines.append(f"  [{status}] {len(batch):>3} projects  {total_files:>6} files  {fmt_bytes(total_size)}")
        for p in batch:
            age_str = ""
            if p.last_modified:
                days = int((time.time() - p.last_modified) / 86400)
                age_str = f"  (last activity {days}d ago)"
            git_mark = " git" if p.has_git else ""
            note_str = f" — {p.note}" if p.note else ""
            lines.append(f"    ├─ {p.name}{git_mark}{note_str}{age_str}")
        lines.append("")

    for leftover_status, batch in sorted(by_status.items()):
        total_files = sum(p.file_count for p in batch)
        total_size = sum(p.total_size for p in batch)
        lines.append(f"  [{leftover_status}] {len(batch):>3} projects  {total_files:>6} files  {fmt_bytes(total_size)}")

    return "\n".join(lines)


def archive_project(
    project: ProjectInfo,
    cfg: CharkiveConfig,
    *,
    dry_run: bool = False,
    archive_dir: Path | None = None,
) -> tuple[bool, str]:
    if project.status == "archived":
        return False, f"{project.name} is already archived"

    dst_root = archive_dir or (cfg.root / "_archive")
    dst = dst_root / project.name

    if dst.exists() and not dry_run:
        return False, f"Archive destination {dst} already exists"

    if dry_run:
        return True, f"Would move {project.name} to {dst_root}"

    src = project.path
    dst.parent.mkdir(parents=True, exist_ok=True)

    write_project_status(src, "archived", note=f"Archived from {project.status} on {time.strftime('%Y-%m-%d')}")

    shutil.move(str(src), str(dst))
    return True, f"Moved {project.name} -> {dst_root}"
