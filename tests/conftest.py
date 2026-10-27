from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from charkive.config import load_config

CONFIG = """\
version: 1
sandbox: true
sanitorium:
  path: .charkive/sanitorium
  retention_days: 30
sanctuary:
  - /Archive/**
protect_extensions:
  - .mov
  - .mp4
sanity_rules:
  - name: shyte_dotfiles
    tier: shyte
    match:
      - .DS_Store
  - name: shyte_scratch_ext
    tier: shyte
    extensions:
      - .tmp
    age_days: 7
  - name: kiloshyte_render_files
    tier: kiloshyte
    path: "**/Render Files/**"
brick_protection:
  enabled: true
  forbidden_paths:
    - /bricks
"""


def make_file(path: Path, data: bytes = b"x", *, age_days: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if age_days:
        t = time.time() - age_days * 86400
        os.utime(path, (t, t))
    return path


@pytest.fixture
def cfg(tmp_path):
    root = tmp_path / "san"
    root.mkdir()
    (root / ".charkive.yml").write_text(CONFIG + f'root: "{root}"\n', encoding="utf-8")
    return load_config(root / ".charkive.yml")
