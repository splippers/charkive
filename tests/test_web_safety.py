import asyncio

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from charkive import db, webapp


def test_remote_web_bind_requires_auth_token(monkeypatch):
    monkeypatch.delenv("CHARKIVE_WEB_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="requires CHARKIVE_WEB_TOKEN"):
        webapp.start_web_server(host="0.0.0.0")


def test_web_auth_rejects_missing_or_wrong_credentials(monkeypatch):
    monkeypatch.setenv("CHARKIVE_WEB_TOKEN", "test-token")

    with pytest.raises(HTTPException) as missing:
        webapp._require_web_auth(None)
    assert missing.value.status_code == 401

    wrong = HTTPBasicCredentials(username="charkive", password="wrong")
    with pytest.raises(HTTPException) as invalid:
        webapp._require_web_auth(wrong)
    assert invalid.value.status_code == 401

    valid = HTTPBasicCredentials(username="charkive", password="test-token")
    assert webapp._require_web_auth(valid) is None


@pytest.mark.parametrize(
    ("tier", "confirmation", "expected_error"),
    [
        ("megashyte", None, "MEGASHYTE"),
        ("gigashyte", "almost eleven", "THESE GO TO ELEVEN"),
    ],
)
def test_web_api_requires_high_tier_confirmation(tier, confirmation, expected_error):
    with pytest.raises(HTTPException, match=expected_error):
        webapp._require_tier_confirmation(tier, confirmation)


def test_web_api_real_quarantine_uses_tier_confirmation(
    monkeypatch, charkive_config, tmp_path
):
    source = tmp_path / "large.render"
    source.write_bytes(b"data")
    state_db = charkive_config.state_db_path()
    conn = db.connect(state_db)
    scan_id = db.start_scan(conn, tmp_path)
    db.bulk_upsert_artifacts(
        conn,
        scan_id=scan_id,
        batch=[("large.render", 4, 1.0, "candidate", "megashyte", "render", None)],
    )
    db.finish_scan(conn, scan_id, 1)
    conn.close()
    monkeypatch.setattr(webapp, "_get_config", lambda: charkive_config)
    monkeypatch.setattr(webapp, "_check_disk_safety", lambda _: None)
    monkeypatch.delenv("CHARKIVE_READONLY", raising=False)

    with pytest.raises(HTTPException) as missing:
        asyncio.run(webapp.api_sanitise({"tier": "megashyte", "dry_run": False}))
    assert missing.value.status_code == 400
    assert source.exists()

    result = asyncio.run(
        webapp.api_sanitise(
            {"tier": "megashyte", "dry_run": False, "confirmation": "MEGASHYTE"}
        )
    )

    assert result["staged"] == 1
    assert not source.exists()


def test_configured_local_volume_skips_gluster_checks(charkive_config):
    assert webapp.sanity_runner.gluster_warnings(charkive_config) == []


def test_web_api_rejects_brick_paths_before_actions(monkeypatch, charkive_config):
    monkeypatch.setattr(webapp, "_get_config", lambda: charkive_config)
    monkeypatch.setattr(webapp, "forbidden_brick_resolve", lambda *_: True)

    with pytest.raises(HTTPException) as blocked:
        webapp._check_disk_safety(charkive_config)

    assert blocked.value.status_code == 403
