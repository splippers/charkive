"""Characterization tests for scan -> quarantine -> restore."""
from __future__ import annotations

import json

import pytest

from charkive import db
from charkive.sanity import run_scan
from charkive.sanitorium import quench, sanitise_moves
from conftest import make_file


@pytest.fixture
def scanned(cfg):
    make_file(cfg.root / "Docs/.DS_Store", b"junk")
    make_file(cfg.root / "Proj/Render Files/r1.bin", b"render" * 10)
    make_file(cfg.root / "Proj/final.mov", b"master" * 10)
    make_file(cfg.root / "Archive/keep.txt", b"keep")
    make_file(cfg.root / "Docs/essay.docx", b"essay")
    scan_id, _stats = run_scan(cfg)
    conn = db.connect(cfg.state_db_path())
    yield cfg, conn, scan_id
    conn.close()


def test_scan_classifies_the_tree(scanned):
    cfg, conn, scan_id = scanned
    rows = dict(conn.execute("SELECT rel_path, status FROM artifacts WHERE scan_id=?", (scan_id,)).fetchall())
    assert rows == {
        "Docs/.DS_Store": "candidate",
        "Proj/Render Files/r1.bin": "candidate",
        "Proj/final.mov": "protect",
        "Archive/keep.txt": "protect",
        "Docs/essay.docx": "review",
    }


def test_dry_run_moves_nothing(scanned):
    cfg, conn, scan_id = scanned
    staged, nbytes = sanitise_moves(cfg, conn, scan_id=scan_id, tier=None, dry_run=True)
    assert len(staged) == 2 and nbytes > 0
    assert (cfg.root / "Docs/.DS_Store").exists()
    assert not cfg.sanitorium_absolute().joinpath("manifest.ndjson").exists()


def test_real_run_quarantines_only_candidates_and_writes_manifest(scanned):
    cfg, conn, scan_id = scanned
    staged, _ = sanitise_moves(cfg, conn, scan_id=scan_id, tier=None, dry_run=False)
    assert len(staged) == 2
    assert not (cfg.root / "Docs/.DS_Store").exists()
    assert (cfg.root / "Proj/final.mov").exists()
    assert (cfg.root / "Archive/keep.txt").exists()
    assert (cfg.root / "Docs/essay.docx").exists()

    manifests = list(cfg.sanitorium_absolute().glob("*/manifest.ndjson"))
    assert len(manifests) == 1
    recs = [json.loads(line) for line in manifests[0].read_text().splitlines()]
    assert {r["from"] for r in recs} == {"Docs/.DS_Store", "Proj/Render Files/r1.bin"}
    assert all(not r["dry_run"] for r in recs)


def test_tier_filter_limits_what_moves(scanned):
    cfg, conn, scan_id = scanned
    staged, _ = sanitise_moves(cfg, conn, scan_id=scan_id, tier="kiloshyte", dry_run=False)
    assert len(staged) == 1
    assert (cfg.root / "Docs/.DS_Store").exists()
    assert not (cfg.root / "Proj/Render Files/r1.bin").exists()


def test_quench_restores_a_quarantined_file(scanned):
    cfg, conn, scan_id = scanned
    sanitise_moves(cfg, conn, scan_id=scan_id, tier=None, dry_run=False)
    bucket = next(p for p in cfg.sanitorium_absolute().iterdir() if p.is_dir())
    quench(cfg, f"{bucket.name}/Docs/.DS_Store")
    assert (cfg.root / "Docs/.DS_Store").read_bytes() == b"junk"


def test_quench_refuses_traversal_out_of_the_sanitorium(scanned):
    cfg, _conn, _scan_id = scanned
    with pytest.raises(RuntimeError):
        quench(cfg, "2026-W01/../../../etc/passwd")


def test_quench_strips_leading_dots_so_it_cannot_start_outside(scanned):
    cfg, _conn, _scan_id = scanned
    with pytest.raises(RuntimeError, match="Unsafe relative path"):
        quench(cfg, "../../etc/passwd")
