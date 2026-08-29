#!/usr/bin/env python3
"""Behavior tests for managed knowledge-base publication verification."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from domain import Chapter, EpisodeMetadata, EpisodeNote, SynthesisSummary, TopicDefinition
from knowledge_base_publisher import (
    KnowledgeBasePublisher,
    PublicationMode,
    PublicationRequest,
)
from topic_synthesizer import TopicGuideSynthesizer


class FixtureEpisodeSynthesizer:
    def __init__(
        self,
        episode_numbers: tuple[int, ...],
        *,
        reject_second_call: bool = False,
    ) -> None:
        self.episode_numbers = episode_numbers
        self.reject_second_call = reject_second_call
        self.call_count = 0

    def synthesize_notes(self, **kwargs) -> SynthesisSummary:
        self.call_count += 1
        if self.reject_second_call and self.call_count > 1:
            raise AssertionError("Episode notes were synthesized more than once")
        notes = tuple(
            EpisodeNote(
                metadata=EpisodeMetadata(
                    number=number,
                    youtube_id=f"video-{number}",
                    youtube_url=f"https://youtube.test/watch?v=video-{number}",
                    youtube_title=f"Fixture YouTube title {number}",
                    display_title=f"Fixture episode {number}",
                    date=f"202{number}-01-0{number}",
                    date_source="fixture",
                    duration_str="1:00",
                    duration_seconds=60,
                    archive_url=f"https://archive.test/EP{number}",
                    summary=f"Fixture summary {number}",
                ),
                chapters=(
                    Chapter(
                        index=1,
                        heading=f"Only topic heading {number}",
                        takeaway=f"Only topic takeaway {number}",
                        excerpts=(f"Only topic evidence {number}",),
                    ),
                ),
            )
            for number in self.episode_numbers
        )
        return SynthesisSummary(
            total_episodes=len(notes),
            total_chapters=len(notes),
            total_seconds=len(notes) * 60,
            chapter_distribution=Counter({1: len(notes)}),
            notes=notes,
        )


class RewritingTopicSynthesizer:
    def __init__(self, guide_slugs: tuple[str, ...]) -> None:
        self.guide_slugs = guide_slugs

    def synthesize_all_topics(self, notes, topics):
        guides = TopicGuideSynthesizer().synthesize_all_topics(notes, topics)
        return [
            replace(guide, definition=replace(guide.definition, slug=slug))
            for guide, slug in zip(guides, self.guide_slugs, strict=True)
        ]


def make_fixture_publisher(
    *,
    episode_numbers: tuple[int, ...],
    topic_slugs: tuple[str, ...],
) -> KnowledgeBasePublisher:
    topics = tuple(
        TopicDefinition(
            slug=slug,
            title=f"Topic {slug}",
            description=f"Fixture guide for {slug}.",
            category="fixture",
            keywords=("Only topic",),
        )
        for slug in topic_slugs
    )
    return KnowledgeBasePublisher(
        episode_synthesizer=FixtureEpisodeSynthesizer(episode_numbers),
        topic_catalog=topics,
    )


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


def test_publish_builds_and_verifies_one_complete_tree(tmp_path):
    publisher = make_fixture_publisher(episode_numbers=(1, 2), topic_slugs=("only-topic",))
    destination = tmp_path / "publication"

    manifest = publisher.publish(PublicationRequest(destination=destination))
    report = publisher.verify(destination)

    assert report.is_valid
    assert manifest.source_episodes == (1, 2)
    assert manifest.topic_catalog == ("only-topic",)
    assert sorted(
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    ) == [
        "README.md",
        "_index.md",
        "episodes/EP0001.full.md",
        "episodes/EP0001.md",
        "episodes/EP0002.full.md",
        "episodes/EP0002.md",
        "publication-manifest.json",
        "topics/README.md",
        "topics/only-topic.md",
    ]


def test_publish_derives_topic_guides_from_one_in_memory_source_batch(tmp_path):
    synthesizer = FixtureEpisodeSynthesizer((1,), reject_second_call=True)
    topic = TopicDefinition(
        slug="only-topic",
        title="Only Topic",
        description="One fixture Topic Guide.",
        category="fixture",
        keywords=("Only topic",),
    )
    publisher = KnowledgeBasePublisher(
        episode_synthesizer=synthesizer,
        topic_catalog=(topic,),
    )
    destination = tmp_path / "publication"

    publisher.publish(PublicationRequest(destination=destination))

    topic_guide = (destination / "topics/only-topic.md").read_text(encoding="utf-8")
    assert synthesizer.call_count == 1
    assert "../episodes/EP0001.md" in topic_guide
    assert "2021-01-01" in topic_guide
    assert "Only topic heading 1" in topic_guide
    assert "Only topic takeaway 1" in topic_guide


def test_publish_replaces_stale_artifacts_and_repeats_without_sibling_debris(tmp_path):
    destination = tmp_path / "publication"
    publisher_a = make_fixture_publisher(
        episode_numbers=(1,),
        topic_slugs=("topic-a",),
    )
    publisher_a.publish(PublicationRequest(destination=destination))

    publisher_b = make_fixture_publisher(
        episode_numbers=(1, 2),
        topic_slugs=("topic-b",),
    )
    manifest_b = publisher_b.publish(PublicationRequest(destination=destination))

    expected_files = {artifact.path for artifact in manifest_b.artifacts}
    expected_files.add("publication-manifest.json")
    actual_files = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    }
    assert actual_files == expected_files
    assert not (destination / "topics/topic-a.md").exists()

    repeated_publisher_b = make_fixture_publisher(
        episode_numbers=(1, 2),
        topic_slugs=("topic-b",),
    )
    repeated_publisher_b.publish(PublicationRequest(destination=destination))

    assert repeated_publisher_b.verify(destination).is_valid
    assert list(tmp_path.glob(".publication.staging-*")) == []
    assert list(tmp_path.glob(".publication.backup-*")) == []


@pytest.mark.parametrize("max_workers", (0, -1))
def test_publish_rejects_non_positive_workers_before_writing(tmp_path, max_workers):
    publisher = make_fixture_publisher(
        episode_numbers=(1,),
        topic_slugs=("only-topic",),
    )
    destination = tmp_path / "publication"

    with pytest.raises(ValueError, match="positive integer"):
        publisher.publish(
            PublicationRequest(destination=destination, max_workers=max_workers)
        )

    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


def test_publish_rejects_the_workspace_root_before_synthesis():
    synthesizer = FixtureEpisodeSynthesizer((1,))
    publisher = KnowledgeBasePublisher(episode_synthesizer=synthesizer)
    workspace_root = Path(__file__).resolve().parent.parent

    with pytest.raises(ValueError, match="protected directory"):
        publisher.publish(PublicationRequest(destination=workspace_root))

    assert synthesizer.call_count == 0


@pytest.mark.parametrize(
    "slug",
    (
        "",
        ".",
        "..",
        "../../outside",
        "topic/subtopic",
        "topic\\subtopic",
        "/absolute",
        "C:\\absolute",
        "C:relative",
        "topic/../normalized",
    ),
)
def test_publish_rejects_an_invalid_topic_slug_before_writing(tmp_path, slug):
    publisher = make_fixture_publisher(
        episode_numbers=(1,),
        topic_slugs=(slug,),
    )
    destination = tmp_path / "publication"

    with pytest.raises(ValueError, match="Topic catalog slug"):
        publisher.publish(
            PublicationRequest(destination=destination, keep_failed_staging=True)
        )

    assert list(tmp_path.iterdir()) == []


def test_publish_rejects_duplicate_topic_slugs_before_writing(tmp_path):
    publisher = make_fixture_publisher(
        episode_numbers=(1,),
        topic_slugs=("duplicate", "duplicate"),
    )
    destination = tmp_path / "publication"

    with pytest.raises(ValueError, match="Topic catalog slugs must be unique"):
        publisher.publish(
            PublicationRequest(destination=destination, keep_failed_staging=True)
        )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "guide_slug",
    (
        "",
        ".",
        "..",
        "../../outside",
        "topic/subtopic",
        "topic\\subtopic",
        "/absolute",
        "C:\\absolute",
        "C:relative",
    ),
)
def test_publish_rejects_an_invalid_guide_slug_before_rendering(tmp_path, guide_slug):
    publisher = make_fixture_publisher(
        episode_numbers=(1,),
        topic_slugs=("only-topic",),
    )
    publisher.topic_synthesizer = RewritingTopicSynthesizer((guide_slug,))
    destination = tmp_path / "publication"

    with pytest.raises(ValueError, match="Topic Guide slug"):
        publisher.publish(
            PublicationRequest(destination=destination, keep_failed_staging=True)
        )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("catalog_slugs", "guide_slugs"),
    (
        (("only-topic",), ("different-topic",)),
        (("topic-a", "topic-b"), ("topic-a", "topic-a")),
    ),
)
def test_publish_rejects_topic_guide_catalog_mismatches_before_rendering(
    tmp_path,
    catalog_slugs,
    guide_slugs,
):
    publisher = make_fixture_publisher(
        episode_numbers=(1,),
        topic_slugs=catalog_slugs,
    )
    publisher.topic_synthesizer = RewritingTopicSynthesizer(guide_slugs)
    destination = tmp_path / "publication"

    with pytest.raises(ValueError, match="exactly match the Topic catalog"):
        publisher.publish(
            PublicationRequest(destination=destination, keep_failed_staging=True)
        )

    assert list(tmp_path.iterdir()) == []


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
