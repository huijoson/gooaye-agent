#!/usr/bin/env python3
"""Behavior tests for managed knowledge-base publication verification."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from knowledge_base_publisher import KnowledgeBasePublisher, PublicationMode


def snapshot_bytes(root: Path) -> dict[str, bytes]:
    """Capture every fixture file without modifying its publication."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def build_managed_fixture(root: Path, *, episodes: tuple[int, ...], topics: tuple[str, ...]) -> Path:
    """Build a minimal complete managed publication with a truthful manifest."""
    artifacts = {
        "README.md": "# Publication\n\n[Browse](_index.md)\n",
        "_index.md": "# Index\n\n[Topics](topics/README.md)\n",
        "topics/README.md": "# Topics\n",
    }
    for number in episodes:
        stem = f"episodes/EP{number:04d}"
        artifacts[f"{stem}.md"] = f"# EP {number}\n\n[Full]({stem.split('/')[-1]}.full.md)\n"
        artifacts[f"{stem}.full.md"] = f"# EP {number} full\n"
    for slug in topics:
        artifacts["topics/README.md"] += f"[{slug}]({slug}.md)\n"
        artifacts[f"topics/{slug}.md"] = f"# {slug}\n\n[EP 1](../episodes/EP{episodes[0]:04d}.md)\n"

    for relative_path, content in artifacts.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "created_at": "2026-08-29T00:00:00Z",
        "source_episodes": list(episodes),
        "topic_catalog": list(topics),
        "total_chapters": len(episodes),
        "total_seconds": len(episodes) * 60,
        "artifacts": [
            {
                "path": relative_path,
                "size_bytes": len(content.encode("utf-8")),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
            for relative_path, content in sorted(artifacts.items())
        ],
    }
    (root / "publication-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return root


def add_manifest_artifact(root: Path, relative_path: str, content: str) -> None:
    """Add a deliberately managed fixture file and keep its Manifest truthful."""
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    manifest_path = root / "publication-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    encoded = content.encode("utf-8")
    manifest["artifacts"].append(
        {
            "path": relative_path,
            "size_bytes": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }
    )
    manifest["artifacts"].sort(key=lambda artifact: artifact["path"])
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_verify_accepts_a_complete_manifest_managed_publication(tmp_path):
    root = build_managed_fixture(
        tmp_path / "publication",
        episodes=(1, 2),
        topics=("only-topic",),
    )
    before = snapshot_bytes(root)

    report = KnowledgeBasePublisher().verify(root)

    assert report.is_valid
    assert report.mode is PublicationMode.MANAGED
    assert report.episode_count == 2
    assert report.topic_count == 1
    assert snapshot_bytes(root) == before


def test_verify_reports_missing_when_a_required_episode_full_note_is_deleted(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    (root / "episodes/EP0001.full.md").unlink()

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert "missing" in {defect.category for defect in report.defects}


def test_verify_reports_digest_when_a_topic_guide_is_tampered(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    (root / "topics/only-topic.md").write_text("# tampered\n", encoding="utf-8")

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert "digest" in {defect.category for defect in report.defects}


def test_verify_reports_stale_when_an_unmanifested_file_is_added(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    (root / "stale.md").write_text("# stale\n", encoding="utf-8")

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert "stale" in {defect.category for defect in report.defects}


def test_verify_reports_broken_link_when_a_local_markdown_target_is_missing(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    (root / "topics/only-topic.md").write_text("[missing](missing.md)\n", encoding="utf-8")

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert "broken_link" in {defect.category for defect in report.defects}


def test_verify_reports_unsafe_path_when_an_artifact_is_an_escaping_symlink(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    outside = tmp_path / "outside.md"
    outside.write_text("# outside\n", encoding="utf-8")
    artifact = root / "episodes/EP0001.full.md"
    artifact.unlink()
    artifact.symlink_to(outside)

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert "unsafe_path" in {defect.category for defect in report.defects}


def test_verify_requires_every_manifest_source_episode_note_pair(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    manifest_path = root / "publication-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"] = [
        artifact for artifact in manifest["artifacts"]
        if artifact["path"] != "episodes/EP0001.full.md"
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert "missing" in {defect.category for defect in report.defects}


def test_verify_reports_unsafe_path_when_a_markdown_link_escapes_root(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    (root / "topics/only-topic.md").write_text("[outside](../../outside.md)\n", encoding="utf-8")

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert "unsafe_path" in {defect.category for defect in report.defects}


def test_verify_rejects_an_unknown_non_empty_directory(tmp_path):
    root = tmp_path / "unknown"
    root.mkdir()
    (root / "personal.txt").write_text("do not own", encoding="utf-8")

    report = KnowledgeBasePublisher().verify(root)

    assert report.mode is PublicationMode.UNKNOWN
    assert {defect.category for defect in report.defects} == {"ownership"}


def test_verify_recognizes_missing_and_empty_destinations_without_ownership_defects(tmp_path):
    missing = tmp_path / "missing"
    empty = tmp_path / "empty"
    empty.mkdir()

    for root in (missing, empty):
        report = KnowledgeBasePublisher().verify(root)

        assert report.mode is PublicationMode.UNKNOWN
        assert report.is_valid


def test_verify_rejects_manifest_artifact_paths_that_are_not_file_paths(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    manifest_path = root / "publication-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["path"] = "."
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = KnowledgeBasePublisher().verify(root)

    assert {defect.category for defect in report.defects} == {"manifest"}


def test_verify_rejects_unsorted_manifest_source_episodes(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1, 2), topics=("only-topic",))
    manifest_path = root / "publication-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_episodes"] = [2, 1]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = KnowledgeBasePublisher().verify(root)

    assert {defect.category for defect in report.defects} == {"manifest"}


@pytest.mark.parametrize(
    "relative_path",
    ("private.txt", "episodes/junk.bin", "topics/uncatalogued.md"),
)
def test_verify_rejects_manifested_artifacts_outside_the_public_tree(tmp_path, relative_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    add_manifest_artifact(root, relative_path, "managed but forbidden\n")

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert "stale" in {defect.category for defect in report.defects}


def test_verify_rejects_an_extra_empty_directory(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    (root / "private").mkdir()

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert "stale" in {defect.category for defect in report.defects}


def test_verify_rejects_an_extra_special_entry(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    os.mkfifo(root / "episodes" / "not-a-note")

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert "stale" in {defect.category for defect in report.defects}


def test_verify_rejects_a_symlinked_manifest_without_reading_its_target(tmp_path, monkeypatch):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    manifest = root / "publication-manifest.json"
    outside = tmp_path / "outside-manifest.json"
    outside.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
    manifest.unlink()
    manifest.symlink_to(outside)
    read_text = Path.read_text

    def reject_external_read(path, *args, **kwargs):
        if path.resolve() == outside:
            raise AssertionError("verify read the external Manifest target")
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", reject_external_read)

    report = KnowledgeBasePublisher().verify(root)

    assert report.mode is PublicationMode.MANAGED
    assert "unsafe_path" in {defect.category for defect in report.defects}


def test_verify_rejects_a_symlinked_artifact_without_opening_its_target(tmp_path, monkeypatch):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    artifact = root / "episodes/EP0001.full.md"
    outside = tmp_path / "outside-note.md"
    outside.write_text("# external\n", encoding="utf-8")
    artifact.unlink()
    artifact.symlink_to(outside)
    open_file = Path.open

    def reject_external_open(path, *args, **kwargs):
        if path.resolve() == outside:
            raise AssertionError("verify opened the external artifact target")
        return open_file(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_external_open)

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert "unsafe_path" in {defect.category for defect in report.defects}


def test_verify_skips_an_artifact_below_a_symlinked_directory(tmp_path, monkeypatch):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    episodes = root / "episodes"
    outside = tmp_path / "outside-episodes"
    episodes.rename(outside)
    episodes.symlink_to(outside, target_is_directory=True)
    open_file = Path.open

    def reject_external_open(path, *args, **kwargs):
        if path.resolve().is_relative_to(outside):
            raise AssertionError("verify opened an artifact below the external directory")
        return open_file(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_external_open)

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert "unsafe_path" in {defect.category for defect in report.defects}


def test_verify_rejects_a_special_manifest_without_reading_it(tmp_path, monkeypatch):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    manifest = root / "publication-manifest.json"
    manifest.unlink()
    os.mkfifo(manifest)
    read_text = Path.read_text

    def reject_manifest_read(path, *args, **kwargs):
        if path == manifest:
            raise AssertionError("verify read the special Manifest entry")
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", reject_manifest_read)

    report = KnowledgeBasePublisher().verify(root)

    assert report.mode is PublicationMode.MANAGED
    assert "unsafe_path" in {defect.category for defect in report.defects}


def test_verify_reports_a_defect_for_non_utf8_markdown_without_raising(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    (root / "topics/only-topic.md").write_bytes(b"\xff")

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert "unreadable" in {defect.category for defect in report.defects}


def test_verify_converts_artifact_stat_failures_to_defects(tmp_path, monkeypatch):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    artifact = root / "topics/only-topic.md"
    stat = Path.stat

    def fail_artifact_stat(path, *args, **kwargs):
        if path == artifact:
            raise OSError("simulated stat failure")
        return stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fail_artifact_stat)

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert report.defects


def test_verify_checks_reference_style_markdown_destinations(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    (root / "topics/only-topic.md").write_text(
        "[outside][outside guide]\n\n[outside guide]: ../../outside.md\n",
        encoding="utf-8",
    )

    report = KnowledgeBasePublisher().verify(root)

    assert "unsafe_path" in {defect.category for defect in report.defects}


def test_verify_accepts_angle_bracket_destinations_with_spaces(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only topic",))
    (root / "topics/README.md").write_text("[topic](<only topic.md>)\n", encoding="utf-8")

    report = KnowledgeBasePublisher().verify(root)

    assert "broken_link" not in {defect.category for defect in report.defects}


def test_verify_decodes_escaped_markdown_destinations(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    (root / "topics/only-topic.md").write_text(
        "[full](../episodes/EP0001\\.full.md)\n",
        encoding="utf-8",
    )

    report = KnowledgeBasePublisher().verify(root)

    assert "broken_link" not in {defect.category for defect in report.defects}


def test_verify_accepts_balanced_parentheses_in_markdown_destinations(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("topic(one)",))

    report = KnowledgeBasePublisher().verify(root)

    assert report.is_valid


def test_verify_decodes_percent_encoded_paths_before_containment_checking(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    (root / "topics/only-topic.md").write_text("[outside](%2e%2e/%2e%2e/outside.md)\n", encoding="utf-8")

    report = KnowledgeBasePublisher().verify(root)

    assert "unsafe_path" in {defect.category for defect in report.defects}


def test_verify_converts_malformed_markdown_destinations_to_defects(tmp_path):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    (root / "topics/only-topic.md").write_text("[bad](//[)\n", encoding="utf-8")

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert report.defects
