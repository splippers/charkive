"""Characterization tests: pin the classification behaviour before it is shared."""
from __future__ import annotations

import os

import pytest

from charkive.fire_codes import FireCodes, parse_size, tier_weight
from conftest import make_file


def classify(cfg, rel, *, age_days=0, data=b"x"):
    fc = FireCodes(cfg.sanctuary, cfg.sanity_rules, cfg.protect_extensions)
    p = make_file(cfg.root / rel, data, age_days=age_days)
    return fc.classify(p, rel, st=os.stat(p))


def test_media_extension_is_protected_anywhere(cfg):
    assert classify(cfg, "Projects/clip.MOV")[0] == "protect"
    assert classify(cfg, "Projects/Render Files/clip.mp4")[0] == "protect"


def test_sanctuary_protects_everything_under_it(cfg):
    assert classify(cfg, "Archive/old/notes.txt")[0] == "protect"
    assert classify(cfg, "Archive/junk/.DS_Store")[0] == "protect"


def test_basename_rule_makes_a_candidate(cfg):
    assert classify(cfg, "Docs/.DS_Store") == ("candidate", "shyte", "shyte_dotfiles")


def test_age_rule_needs_old_enough_file(cfg):
    assert classify(cfg, "Docs/new.tmp")[0] == "review"
    assert classify(cfg, "Docs/old.tmp", age_days=10) == ("candidate", "shyte", "shyte_scratch_ext")


def test_path_rule_matches_glob(cfg):
    assert classify(cfg, "Proj/Render Files/a.bin") == ("candidate", "kiloshyte", "kiloshyte_render_files")


def test_unmatched_files_are_review_only(cfg):
    assert classify(cfg, "Docs/essay.docx") == ("review", None, None)


def test_highest_tier_wins_when_rules_overlap(tmp_path):
    rules = (
        {"name": "low", "tier": "shyte", "match": ["a.bin"]},
        {"name": "high", "tier": "megashyte", "match": ["a.bin"]},
    )
    fc = FireCodes((), rules, frozenset())
    p = make_file(tmp_path / "a.bin")
    assert fc.classify(p, "a.bin", st=os.stat(p)) == ("candidate", "megashyte", "high")


def test_sibling_requirement_blocks_when_parent_clip_exists(tmp_path):
    rules = ({"name": "orphan", "tier": "shyte", "extensions": [".xmp"], "require_no_sibling": [".mov"]},)
    fc = FireCodes((), rules, frozenset())
    xmp = make_file(tmp_path / "clip.xmp")
    assert fc.classify(xmp, "clip.xmp", st=os.stat(xmp))[0] == "candidate"
    make_file(tmp_path / "clip.mov")
    assert fc.classify(xmp, "clip.xmp", st=os.stat(xmp))[0] == "review"


def test_immutable_xattr_protects(tmp_path):
    if not hasattr(os, "setxattr"):
        pytest.skip("no xattr support")
    rules = ({"name": "any", "tier": "shyte", "match": ["a.bin"]},)
    fc = FireCodes((), rules, frozenset())
    p = make_file(tmp_path / "a.bin")
    try:
        os.setxattr(p, "user.immutable", b"1")
    except OSError:
        pytest.skip("filesystem rejects user xattrs")
    assert fc.classify(p, "a.bin", st=os.stat(p))[0] == "protect"


@pytest.mark.parametrize(
    "spec,want",
    [(100, 100), ("1kb", 1024), ("2 MB", 2 * 1024**2), ("1.5gb", int(1.5 * 1024**3)), ("", 0)],
)
def test_parse_size(spec, want):
    assert parse_size(spec) == want


def test_tier_weights_are_ordered():
    assert tier_weight("shyte") < tier_weight("kiloshyte") < tier_weight("megashyte") < tier_weight("gigashyte")
    assert tier_weight("nonsense") == 0 and tier_weight(None) == 0


def meta(rel, *, size=1, age_days=0.0, atime=None, immutable=False, now=1_000_000_000.0):
    from charkive.fire_codes import FileMeta

    return FileMeta(rel_posix=rel, size=size, mtime=now - age_days * 86400, atime=atime, immutable=immutable), now


def test_classify_meta_works_without_a_local_file(cfg):
    fc = FireCodes(cfg.sanctuary, cfg.sanity_rules, cfg.protect_extensions)
    m, now = meta("Photos/trip.mp4")
    assert fc.classify_meta(m, now=now)[0] == "protect"
    m, now = meta("Docs/.DS_Store")
    assert fc.classify_meta(m, now=now) == ("candidate", "shyte", "shyte_dotfiles")
    m, now = meta("Docs/old.tmp", age_days=10)
    assert fc.classify_meta(m, now=now)[0] == "candidate"
    m, now = meta("Docs/new.tmp", age_days=1)
    assert fc.classify_meta(m, now=now)[0] == "review"


def test_classify_meta_honours_immutable_flag():
    fc = FireCodes((), ({"name": "any", "tier": "shyte", "match": ["a.bin"]},), frozenset())
    m, now = meta("a.bin", immutable=True)
    assert fc.classify_meta(m, now=now)[0] == "protect"


def test_atime_rule_fails_closed_when_backend_has_no_atime():
    rules = ({"name": "cold", "tier": "shyte", "match": ["a.bin"], "atime_days": 30},)
    fc = FireCodes((), rules, frozenset())
    m, now = meta("a.bin", atime=None)
    assert fc.classify_meta(m, now=now)[0] == "review"
    m, now = meta("a.bin", atime=1_000_000_000.0 - 40 * 86400)
    assert fc.classify_meta(m, now=now)[0] == "candidate"
