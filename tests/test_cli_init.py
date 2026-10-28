from typer.testing import CliRunner

from charkive.cli import app


def test_init_requires_existing_disk_root(tmp_path):
    root = tmp_path / "not-mounted"
    result = CliRunner().invoke(app, ["init", str(root)])

    assert result.exit_code == 2
    assert "mount the disk first" in result.output
    assert not root.exists()


def test_init_accepts_local_filesystem_directory(tmp_path):
    root = tmp_path / "removable-disk"
    root.mkdir()
    result = CliRunner().invoke(app, ["init", str(root)])

    assert result.exit_code == 0
    config = (root / ".charkive.yml").read_text()
    assert f'root: "{root}"' in config
    assert "gluster:\n  volume: \"\"" in config
