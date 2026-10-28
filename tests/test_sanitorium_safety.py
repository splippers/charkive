import errno
import sqlite3
from pathlib import Path

import pytest

from charkive import db, sanitorium


def _candidate_db(root: Path, rel_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    db.migrate(conn)
    scan_id = db.start_scan(conn, root)
    db.bulk_upsert_artifacts(
        conn,
        scan_id=scan_id,
        batch=[(rel_path, 4, 1.0, "candidate", "shyte", "scratch", None)],
    )
    conn.commit()
    return conn


def test_sanitise_refuses_existing_quarantine_destination(charkive_config, tmp_path):
    source = tmp_path / "scratch.tmp"
    source.write_bytes(b"keep")
    conn = _candidate_db(tmp_path, "scratch.tmp")
    destination = charkive_config.sanitorium_absolute() / sanitorium._iso_week_dir() / "scratch.tmp"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"existing")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        sanitorium.sanitise_moves(charkive_config, conn, scan_id=1, tier=None, dry_run=False)

    assert source.read_bytes() == b"keep"
    assert destination.read_bytes() == b"existing"
    assert conn.execute("SELECT status FROM artifacts").fetchone()[0] == "candidate"


def test_sanitise_and_restore_move_without_overwrite(charkive_config, tmp_path):
    source = tmp_path / "scratch.tmp"
    source.write_bytes(b"data")
    conn = _candidate_db(tmp_path, "scratch.tmp")

    staged, moved = sanitorium.sanitise_moves(
        charkive_config, conn, scan_id=1, tier=None, dry_run=False
    )

    assert staged == [1]
    assert moved == len(b"data")
    quarantine_path = charkive_config.sanitorium_absolute() / sanitorium._iso_week_dir() / "scratch.tmp"
    assert not source.exists()
    assert quarantine_path.read_bytes() == b"data"

    sanitorium.quench(
        charkive_config, f"{sanitorium._iso_week_dir()}/scratch.tmp"
    )
    assert source.read_bytes() == b"data"
    assert not quarantine_path.exists()


def test_restore_refuses_to_replace_existing_file(charkive_config, tmp_path):
    san_root = charkive_config.sanitorium_absolute()
    source = san_root / "2026-W43" / "scratch.tmp"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"quarantined")
    destination = tmp_path / "scratch.tmp"
    destination.write_bytes(b"keep")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        sanitorium.quench(charkive_config, "2026-W43/scratch.tmp")

    assert source.read_bytes() == b"quarantined"
    assert destination.read_bytes() == b"keep"


def test_moves_on_filesystems_without_hardlink_support(monkeypatch, tmp_path):
    source = tmp_path / "source.tmp"
    destination = tmp_path / "destination.tmp"
    source.write_bytes(b"removable filesystem")

    def unsupported_link(*args, **kwargs):
        raise OSError(errno.EPERM, "hard links unsupported")

    monkeypatch.setattr(sanitorium.os, "link", unsupported_link)
    sanitorium._move_no_replace(source, destination)

    assert not source.exists()
    assert destination.read_bytes() == b"removable filesystem"


def test_sanitise_rejects_traversal_in_scan_state(charkive_config, tmp_path):
    outside = tmp_path.parent / "outside.tmp"
    outside.write_bytes(b"untouched")
    conn = _candidate_db(tmp_path, "../outside.tmp")

    with pytest.raises(RuntimeError, match="Unsafe relative path"):
        sanitorium.sanitise_moves(charkive_config, conn, scan_id=1, tier=None, dry_run=False)

    assert outside.read_bytes() == b"untouched"


def test_sanitise_and_restore_reject_raw_brick_root(charkive_config, tmp_path):
    (tmp_path / ".glusterfs").mkdir()
    source = tmp_path / "scratch.tmp"
    source.write_bytes(b"untouched")
    conn = _candidate_db(tmp_path, "scratch.tmp")

    with pytest.raises(RuntimeError, match="Brick protection rejected"):
        sanitorium.sanitise_moves(charkive_config, conn, scan_id=1, tier=None, dry_run=False)
    with pytest.raises(RuntimeError, match="Brick protection rejected"):
        sanitorium.quench(charkive_config, "2026-W43/scratch.tmp")

    assert source.read_bytes() == b"untouched"
