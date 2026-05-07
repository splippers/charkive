from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_file: Path) -> sqlite3.Connection:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at REAL NOT NULL,
            finished_at REAL,
            root TEXT NOT NULL,
            artifact_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
            rel_path TEXT NOT NULL,
            bytes INTEGER NOT NULL,
            status TEXT NOT NULL,
            tier TEXT,
            rule_name TEXT,
            partial_hash TEXT,
            mtime REAL,
            UNIQUE(scan_id, rel_path)
        );
        CREATE INDEX IF NOT EXISTS ix_artifacts_scan_status
            ON artifacts(scan_id, status);
        CREATE INDEX IF NOT EXISTS ix_artifacts_scan_tier
            ON artifacts(scan_id, tier);
        """
    )
    conn.commit()


def start_scan(conn: sqlite3.Connection, root: Path) -> int:
    import time as _t

    cur = conn.execute(
        "INSERT INTO scans(started_at,finished_at,root) VALUES (?,?,?)",
        (_t.time(), None, str(root.resolve())),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_scan(conn: sqlite3.Connection, scan_id: int, count: int) -> None:
    import time as _t

    conn.execute(
        "UPDATE scans SET finished_at=?, artifact_count=? WHERE id=?",
        (_t.time(), count, scan_id),
    )
    conn.commit()


def bulk_upsert_artifacts(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    batch: list[tuple[str, int, float, str, str | None, str | None, str | None]],
) -> None:
    rows = [(scan_id, rp, nbytes, mt, st, tier, rn, ph) for (rp, nbytes, mt, st, tier, rn, ph) in batch]
    conn.executemany(
        """INSERT INTO artifacts(scan_id, rel_path, bytes, mtime, status, tier, rule_name, partial_hash)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(scan_id, rel_path) DO UPDATE SET
                 bytes=excluded.bytes,
                 mtime=excluded.mtime,
                 status=excluded.status,
                 tier=excluded.tier,
                 rule_name=excluded.rule_name,
                 partial_hash=excluded.partial_hash
        """,
        rows,
    )


def delete_scan(conn: sqlite3.Connection, scan_id: int) -> None:
    conn.execute("DELETE FROM scans WHERE id=?", (scan_id,))
    conn.commit()


def latest_scan(conn: sqlite3.Connection) -> tuple[int, float | None] | None:
    row = conn.execute(
        "SELECT id, finished_at FROM scans ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return int(row[0]), row[1]


def summary_for_scan(conn: sqlite3.Connection, scan_id: int) -> dict:
    cur_s = conn.execute(
        "SELECT status, SUM(bytes), COUNT(*) FROM artifacts WHERE scan_id=? GROUP BY status",
        (scan_id,),
    )
    by_status: dict[str, dict[str, int]] = {}
    for st, sb, fc in cur_s.fetchall():
        by_status[str(st)] = {"bytes": int(sb or 0), "files": int(fc or 0)}

    cur_t = conn.execute(
        """SELECT tier, SUM(bytes), COUNT(*) FROM artifacts WHERE scan_id=? AND status='candidate'
                      AND tier IS NOT NULL GROUP BY tier""",
        (scan_id,),
    )
    by_tier: dict[str | None, dict[str, int]] = {}
    for tier, tb, fc in cur_t.fetchall():
        by_tier[str(tier)] = {"bytes": int(tb or 0), "files": int(fc or 0)}

    fluff_row = conn.execute(
        "SELECT SUM(bytes), COUNT(*) FROM artifacts WHERE scan_id=? AND status='candidate'",
        (scan_id,),
    ).fetchone()
    fluff_bytes = int(fluff_row[0] or 0)
    fluff_files = int(fluff_row[1] or 0)

    protected = by_status.get("protect", {"bytes": 0, "files": 0})
    review_only = by_status.get("review", {"bytes": 0, "files": 0})

    totals = conn.execute(
        "SELECT SUM(bytes), COUNT(*) FROM artifacts WHERE scan_id=?",
        (scan_id,),
    ).fetchone()
    grand_bytes = int(totals[0] or 0)
    grand_files = int(totals[1] or 0)

    return {
        "by_status": by_status,
        "by_tier": by_tier,
        "fluff": {"bytes": fluff_bytes, "files": fluff_files},
        "protected": protected,
        "review": {"bytes": review_only["bytes"], "files": review_only["files"]},
        "grand": {"bytes": grand_bytes, "files": grand_files},
    }


def candidates(
    conn: sqlite3.Connection,
    scan_id: int,
    *,
    tier_filter: str | None = None,
) -> list[tuple[int, str, int]]:
    if tier_filter:
        cur = conn.execute(
            """SELECT id, rel_path, bytes FROM artifacts WHERE scan_id=? AND status='candidate'
                                              AND tier=? ORDER BY tier DESC, bytes DESC""",
            (scan_id, tier_filter.lower()),
        )
        return [(int(a), rp, nb) for (a, rp, nb) in cur.fetchall()]
    cur = conn.execute(
        """SELECT id, rel_path, bytes FROM artifacts WHERE scan_id=? AND status='candidate'
                                  ORDER BY bytes DESC""",
        (scan_id,),
    )
    return [(int(a), rp, nb) for (a, rp, nb) in cur.fetchall()]


def mark_quarantined(
    conn: sqlite3.Connection,
    *,
    ids: list[int],
) -> None:
    q = ",".join("?" * len(ids))
    conn.execute(
        f"UPDATE artifacts SET status='quarantined' WHERE id IN ({q}) AND status='candidate'",
        tuple(ids),
    )
    conn.commit()
