from pathlib import Path

import pytest

from charkive import config as config_module
from charkive.config import load_config, verify_filesystem_identity


def test_init_records_mountpoint_and_device(tmp_path):
    root = tmp_path / "archive"
    root.mkdir()
    config_path = config_module.ensure_config_near_root_written(root)
    config = load_config(config_path)

    assert config.filesystem_mountpoint is not None
    assert config.filesystem_device is not None
    verify_filesystem_identity(config)


def test_changed_mount_identity_blocks_access(tmp_path, monkeypatch):
    root = tmp_path / "archive"
    root.mkdir()
    config_path = config_module.ensure_config_near_root_written(root)
    config = load_config(config_path)
    monkeypatch.setattr(
        config_module,
        "filesystem_identity",
        lambda _root: {"mountpoint": str(root), "device": "999:999"},
    )

    with pytest.raises(RuntimeError, match="filesystem identity changed"):
        verify_filesystem_identity(config)
