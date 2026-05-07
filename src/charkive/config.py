from __future__ import annotations

import os
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
  forbidden_paths:
    - /SANDIEGO
    - /bricks

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

    def state_db_path(self) -> Path:
        return self.root / ".charkive" / "charkive.db"

    def sanitorium_absolute(self) -> Path:
        rp = self.sanitorium.relative_path
        return (self.root / rp).resolve()


def ensure_config_near_root_written(root: Path) -> Path:
    dest = root / DEFAULT_CONFIG_NAME
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = DEFAULT_YAML_BODY + f'\nroot: "{root}"\n'
    dest.write_text(body, encoding="utf-8")
    return dest


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
        forbidden_paths=tuple(str(x) for x in (bb.get("forbidden_paths") or ["/SANDIEGO", "/bricks"])),
    )

    vol_block = raw.get("gluster") or {}
    gv = vol_block.get("volume")
    gv_str = None
    if isinstance(gv, str) and gv.strip():
        gv_str = gv.strip()

    gluster = GlusterCfg(volume=gv_str, pre_sanity_checks=vol_block.get("pre_sanity_checks"))

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
    )
