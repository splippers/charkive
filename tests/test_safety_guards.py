from types import SimpleNamespace

import pytest

from charkive import sanity
from charkive.config import BrickCfg, GlusterCfg
from charkive.paths import forbidden_brick_resolve


def test_brick_marker_on_ancestor_is_detected(tmp_path, charkive_config):
    brick = tmp_path / "brick"
    nested = brick / "subdir"
    nested.mkdir(parents=True)
    (brick / ".glusterfs").mkdir()

    assert forbidden_brick_resolve(nested, charkive_config.brick)


def test_local_mount_path_is_not_reserved(tmp_path):
    assert not forbidden_brick_resolve(
        tmp_path, BrickCfg(enabled=True, forbidden_paths=())
    )


@pytest.mark.parametrize(
    ("heal_stdout", "status_stdout", "error"),
    [
        ("Number of entries: 0\n", "Brick: node:/brick\nOnline: Y\n", None),
        ("", "Brick: node:/brick\nOnline: Y\n", "unrecognized"),
        ("Number of entries: 1\n", "Brick: node:/brick\nOnline: Y\n", "heal entries"),
        ("Number of entries: 0\n", "Brick: node:/brick\nOnline: N\n", "unhealthy"),
    ],
)
def test_gluster_preflight_requires_recognized_healthy_output(
    monkeypatch, charkive_config, heal_stdout, status_stdout, error
):
    charkive_config.gluster = GlusterCfg("testvol")
    monkeypatch.setattr(sanity.shutil, "which", lambda _: "/usr/bin/gluster")
    responses = iter(
        [
            SimpleNamespace(returncode=0, stdout=heal_stdout, stderr=""),
            SimpleNamespace(returncode=0, stdout=status_stdout, stderr=""),
        ]
    )
    monkeypatch.setattr(sanity.subprocess, "run", lambda *args, **kwargs: next(responses))

    if error:
        with pytest.raises(RuntimeError, match=error):
            sanity.gluster_warnings(charkive_config)
    else:
        assert sanity.gluster_warnings(charkive_config) == []


def test_gluster_preflight_fails_when_cli_is_missing(monkeypatch, charkive_config):
    charkive_config.gluster = GlusterCfg("testvol")
    monkeypatch.setattr(sanity.shutil, "which", lambda _: None)

    with pytest.raises(RuntimeError, match="not installed"):
        sanity.gluster_warnings(charkive_config)
