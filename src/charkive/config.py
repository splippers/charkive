from __future__ import annotations

import os
import re
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PROTECT_EXTENSIONS = frozenset(
    {
        ".mov",
        ".mp4",
        ".mxf",
        ".braw",
        ".r3d",
        ".ari",
        ".dpx",
        ".exr",
        ".cin",
        ".wav",
        ".aif",
        ".flac",
        ".psd",
        ".psb",
        ".tiff",
        ".tif",
        ".cr2",
        ".cr3",
        ".nef",
        ".arw",
        ".raf",
        ".aac",
        ".m4a",
        ".fcpxml",
        ".prproj",
    }
)


DEFAULT_CONFIG_NAME = ".charkive.yml"

DEFAULT_YAML_BODY = """# Charkive — burn fluff, guard masters (spec in README).
version: 1
sandbox: true
sanitorium:
  path: .charkive/sanitorium
  retention_days: 30

sanctuary:
  - /Archive/**
  - /Masters/**
  - /Originals/**
  - /Camera/**
  - /Deliverables/**

protect_extensions:
  - .mov
  - .mp4
  - .mxf
  - .braw
  - .r3d
  - .wav
  - .aif

sanity_rules:
  - name: shyte_dotfiles
    tier: shyte
    match:
      - .DS_Store
      - Thumbs.db
  - name: kiloshyte_media_cache
    tier: kiloshyte
    path: "**/Media Cache*/**"
    age_days: 30
  - name: kiloshyte_render_files
    tier: kiloshyte
    path: "**/Render Files/**"
    age_days: 14
  - name: shyte_scratch_ext
    tier: shyte
    extensions:
      - .tmp
      - .bak
      - .pek
      - .cfa
    age_days: 7

brick_protection:
  enabled: true
  forbidden_paths: []

gluster:
  volume: ""

spinal_tap_mode: false
"""


def _normalize_ext(e: Any) -> str:
    raw = str(e).strip().lower().lstrip(".")
    return f".{raw}" if raw else ""


def _normalize_extensions(items: Any) -> frozenset[str]:
    if not items:
        return DEFAULT_PROTECT_EXTENSIONS
    return frozenset(_normalize_ext(x) for x in items)


@dataclass
class GlusterCfg:
    volume: str | None
    pre_sanity_checks: dict[str, Any] | None = None


@dataclass
class BrickCfg:
    enabled: bool
    forbidden_paths: tuple[str, ...]


@dataclass
class SanitoriumCfg:
    relative_path: Path
    retention_days: int


@dataclass
class CharkiveConfig:
    version: int
    root: Path
    sandbox: bool
    sanitorium: SanitoriumCfg
    sanctuary: tuple[str, ...]
    sanity_rules: tuple[dict[str, Any], ...]
    protect_extensions: frozenset[str]
    brick: BrickCfg
    gluster: GlusterCfg
    spinal_tap_mode: bool
    source_file: Path
    filesystem_mountpoint: Path | None = None
    filesystem_device: str | None = None

    def state_db_path(self) -> Path:
        return self.root / ".charkive" / "charkive.db"

    def sanitorium_absolute(self) -> Path:
        rp = self.sanitorium.relative_path
        return (self.root / rp).resolve()


def ensure_config_near_root_written(root: Path) -> Path:
    dest = root / DEFAULT_CONFIG_NAME
    if dest.exists():
        with dest.open(encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or {}
        if "filesystem_guard" not in existing:
            identity = filesystem_identity(root)
            with dest.open("a", encoding="utf-8") as fh:
                fh.write(
                    "\nfilesystem_guard:\n"
                    f"  mountpoint: {json.dumps(str(identity['mountpoint']))}\n"
                    f"  device: {json.dumps(identity['device'])}\n"
                )
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    identity = filesystem_identity(root)
    body = (
        DEFAULT_YAML_BODY
        + f"\nroot: {json.dumps(str(root))}\n"
        + "filesystem_guard:\n"
        + f"  mountpoint: {json.dumps(str(identity['mountpoint']))}\n"
        + f"  device: {json.dumps(identity['device'])}\n"
    )
    dest.write_text(body, encoding="utf-8")
    return dest


def filesystem_identity(root: Path) -> dict[str, str]:
    """Identify the mounted filesystem containing root on Linux."""
    resolved = root.expanduser().resolve(strict=True)
    device_stat = resolved.stat()
    device = f"{os.major(device_stat.st_dev)}:{os.minor(device_stat.st_dev)}"
    mountinfo = Path("/proc/self/mountinfo")
    if not mountinfo.is_file():
        raise RuntimeError("Cannot verify storage mount identity: /proc/self/mountinfo is unavailable.")

    matches: list[Path] = []
    with mountinfo.open(encoding="utf-8") as fh:
        for line in fh:
            fields = line.split(" - ", 1)[0].split()
            if len(fields) < 5:
                continue
            mountpoint = re.sub(
                r"\\([0-7]{3})",
                lambda match: chr(int(match.group(1), 8)),
                fields[4],
            )
            point = Path(mountpoint)
            try:
                resolved.relative_to(point)
                matches.append(point)
            except ValueError:
                continue
    if not matches:
        raise RuntimeError(f"Cannot identify the mounted filesystem containing {resolved}.")
    return {"mountpoint": str(max(matches, key=lambda point: len(point.parts))), "device": device}


def verify_filesystem_identity(config: CharkiveConfig) -> None:
    if config.filesystem_mountpoint is None or config.filesystem_device is None:
        return
    current = filesystem_identity(config.root)
    if (
        current["mountpoint"] != str(config.filesystem_mountpoint)
        or current["device"] != config.filesystem_device
    ):
        raise RuntimeError(
            "Configured storage filesystem identity changed; refusing to scan or move files. "
            "Mount the original filesystem or reinitialize Charkive for this root."
        )


def load_config(config_path: Path | None = None) -> CharkiveConfig:
    base = Path.cwd()
    fp = (base / DEFAULT_CONFIG_NAME) if config_path is None else Path(config_path)
    if not fp.is_file():
        raise FileNotFoundError(f"Missing {fp}. Run: charkive init <ROOT>")
    with fp.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    root_s = raw.get("root") or os.environ.get("CHARKIVE_ROOT")
    if not root_s:
        root_s = str(base.resolve())
    root = Path(root_s).expanduser().resolve()

    sandbox = bool(raw.get("sandbox", False))

    sani_block = raw.get("sanitorium") or raw.get("quarantine") or {}
    qp_raw = sani_block.get("path") or ".charkive/sanitorium"
    qp = Path(str(qp_raw))
    retention = int(sani_block.get("retention_days", 30))

    sanctuary_in = raw.get("sanctuary") or ()
    sanctuary: tuple[str, ...]
    if isinstance(sanctuary_in, dict) and "paths" in sanctuary_in:
        sanctuary = tuple(str(x).lstrip("/").replace("//", "/") for x in sanctuary_in["paths"])
    elif isinstance(sanctuary_in, (list, tuple)):
        sanctuary = tuple(str(x).lstrip("/").replace("//", "/") for x in sanctuary_in)
    else:
        sanctuary = ()

    sr = raw.get("sanity_rules") or raw.get("kindling") or ()
    if not isinstance(sr, (list, tuple)):
        sanity_rules: tuple[dict[str, Any], ...] = ()
    else:
        sanity_rules = tuple(dict(x) for x in sr if isinstance(x, dict))

    protect_extensions = _normalize_extensions(raw.get("protect_extensions"))

    bb = raw.get("brick_protection") or {}
    brick = BrickCfg(
        enabled=bool(bb.get("enabled", True)),
        forbidden_paths=tuple(str(x) for x in bb.get("forbidden_paths", ())),
    )

    vol_block = raw.get("gluster") or {}
    gv = vol_block.get("volume")
    gv_str = None
    if isinstance(gv, str) and gv.strip():
        gv_str = gv.strip()

    gluster = GlusterCfg(volume=gv_str, pre_sanity_checks=vol_block.get("pre_sanity_checks"))
    filesystem_guard = raw.get("filesystem_guard") or {}
    mountpoint_value = filesystem_guard.get("mountpoint")
    device_value = filesystem_guard.get("device")
    if bool(mountpoint_value) != bool(device_value):
        raise ValueError("filesystem_guard must specify both mountpoint and device.")

    return CharkiveConfig(
        version=int(raw.get("version", 1)),
        root=root,
        sandbox=sandbox,
        sanitorium=SanitoriumCfg(relative_path=qp, retention_days=retention),
        sanctuary=sanctuary,
        sanity_rules=sanity_rules,
        protect_extensions=protect_extensions,
        brick=brick,
        gluster=gluster,
        spinal_tap_mode=bool(raw.get("spinal_tap_mode", False)),
        source_file=fp.resolve(),
        filesystem_mountpoint=Path(mountpoint_value) if mountpoint_value else None,
        filesystem_device=str(device_value) if device_value else None,
    )
