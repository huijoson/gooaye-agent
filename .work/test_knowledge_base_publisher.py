#!/usr/bin/env python3
"""Behavior tests for managed knowledge-base publication verification."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import threading
import time
import warnings
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from domain import Chapter, EpisodeMetadata, EpisodeNote, SynthesisSummary, TopicDefinition
from knowledge_base_publisher import (
    KnowledgeBasePublisher,
    PublicationDefect,
    PublicationError,
    PublicationMode,
    PublicationPhase,
    PublicationRequest,
    PublicationVerification,
    _PublicationLock,
)
from markdown_renderer import MarkdownRenderer
from topic_synthesizer import TopicGuideSynthesizer


class FixtureEpisodeSynthesizer:
    def __init__(
        self,
        episode_numbers: tuple[int, ...],
        *,
        reject_second_call: bool = False,
        block_during_synthesis: bool = False,
    ) -> None:
        self.episode_numbers = episode_numbers
        self.reject_second_call = reject_second_call
        self.block_during_synthesis = block_during_synthesis
        self.call_count = 0
        self.synthesis_started = threading.Event()
        self.continue_synthesis = threading.Event()

    def synthesize_notes(self, **kwargs) -> SynthesisSummary:
        self.call_count += 1
        if self.reject_second_call and self.call_count > 1:
            raise AssertionError("Episode notes were synthesized more than once")
        if self.block_during_synthesis and self.call_count == 1:
            self.synthesis_started.set()
            if not self.continue_synthesis.wait(timeout=5):
                raise TimeoutError("Fixture synthesis was not released")
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


class RaisingEpisodeSynthesizer:
    def synthesize_notes(self, **kwargs):
        raise OSError("fixture synthesis failure")


class RaisingMarkdownRenderer(MarkdownRenderer):
    def render_episode(self, note, mode="slim"):
        raise OSError("fixture render failure")


class BrokenLinkMarkdownRenderer(MarkdownRenderer):
    def render_readme(self, notes, summary):
        return "# Publication\n\n[missing](missing.md)\n"


class DestinationMutatingMarkdownRenderer(MarkdownRenderer):
    def __init__(self, destination: Path) -> None:
        self.destination = destination
        self.changed_destination = False

    def render_episode(self, note, mode="slim"):
        if not self.changed_destination:
            self.destination.mkdir()
            (self.destination / "personal.txt").write_text("do not own", encoding="utf-8")
            self.changed_destination = True
        return super().render_episode(note, mode=mode)


def make_fixture_publisher(
    *,
    episode_numbers: tuple[int, ...] = (1,),
    topic_slugs: tuple[str, ...] = ("only-topic",),
    block_during_synthesis: bool = False,
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
        episode_synthesizer=FixtureEpisodeSynthesizer(
            episode_numbers,
            block_during_synthesis=block_during_synthesis,
        ),
        topic_catalog=topics,
    )


@contextmanager
def publisher_held_in_background(publisher, request):
    errors = []

    def run() -> None:
        try:
            publisher.publish(request)
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=run)
    worker.start()
    assert publisher.episode_synthesizer.synthesis_started.wait(timeout=2)
    try:
        yield
    finally:
        publisher.episode_synthesizer.continue_synthesis.set()
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert not errors


def snapshot_bytes(root: Path) -> dict[str, bytes]:
    """Capture every fixture file without modifying its publication."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def no_sibling_staging_or_backup(destination: Path) -> bool:
    return not list(destination.parent.glob(f".{destination.name}.staging-*")) and not list(
        destination.parent.glob(f".{destination.name}.backup-*")
    ) and not list(
        destination.parent.glob(f".{destination.name}.recovery-*")
    )


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


def test_publication_error_exposes_its_phase_and_diagnostics(tmp_path):
    defect = object()
    staging = tmp_path / ".publication.staging-fixture"

    error = PublicationError(
        PublicationPhase.VERIFY,
        "fixture verification failure",
        defects=(defect,),
        staging_path=staging,
    )

    assert str(error) == "fixture verification failure"
    assert error.phase is PublicationPhase.VERIFY
    assert error.defects == (defect,)
    assert error.staging_path == staging


def test_second_publisher_fails_fast_while_destination_is_locked(tmp_path):
    destination = tmp_path / "publication"
    publisher = make_fixture_publisher(block_during_synthesis=True)

    with publisher_held_in_background(publisher, PublicationRequest(destination)):
        started = time.monotonic()
        with pytest.raises(PublicationError) as raised:
            publisher.publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.LOCK
    assert time.monotonic() - started < 1.0


def test_stale_lock_for_another_destination_remains_locked(tmp_path):
    destination = tmp_path / "publication"
    lock = tmp_path / ".publication.publication.lock"
    lock.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "destination": str((tmp_path / "other").resolve()),
                "pid": 999_999_999,
                "hostname": socket.gethostname(),
                "created_at": (datetime.now(timezone.utc) - timedelta(hours=25))
                .isoformat()
                .replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PublicationError) as raised:
        make_fixture_publisher().publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.LOCK
    assert lock.exists()
    assert not destination.exists()


def test_symlinked_stale_lock_remains_locked_without_reading_its_target(tmp_path):
    destination = tmp_path / "publication"
    lock = tmp_path / ".publication.publication.lock"
    outside = tmp_path / "outside-lock.json"
    outside.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "destination": str(destination.resolve()),
                "pid": 999_999_999,
                "hostname": socket.gethostname(),
                "created_at": (datetime.now(timezone.utc) - timedelta(hours=25))
                .isoformat()
                .replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )
    lock.symlink_to(outside)

    with pytest.raises(PublicationError) as raised:
        make_fixture_publisher().publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.LOCK
    assert lock.is_symlink()
    assert outside.exists()


def test_same_host_dead_stale_lock_is_recovered(tmp_path):
    destination = tmp_path / "publication"
    lock = tmp_path / ".publication.publication.lock"
    lock.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "destination": str(destination.resolve()),
                "pid": 999_999_999,
                "hostname": socket.gethostname(),
                "created_at": (datetime.now(timezone.utc) - timedelta(hours=25))
                .isoformat()
                .replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )

    make_fixture_publisher().publish(PublicationRequest(destination))

    assert json.loads(lock.read_text(encoding="utf-8"))["active"] is False
    assert KnowledgeBasePublisher().verify(destination).is_valid


@pytest.mark.parametrize("pid", ("not-a-pid", True, 0, 10**100))
def test_malformed_or_out_of_range_stale_lock_pid_remains_locked(tmp_path, pid):
    destination = tmp_path / "publication"
    lock = tmp_path / ".publication.publication.lock"
    lock.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "destination": str(destination.resolve()),
                "pid": pid,
                "hostname": socket.gethostname(),
                "created_at": (datetime.now(timezone.utc) - timedelta(hours=25))
                .isoformat()
                .replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PublicationError) as raised:
        make_fixture_publisher().publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.LOCK
    assert lock.exists()


def test_lock_release_never_unlinks_an_interleaved_replacement(tmp_path, monkeypatch):
    destination = tmp_path / "publication"
    lock = _PublicationLock(destination)
    lock.acquire()
    write = os.write
    replacement_written = False

    def replace_during_release(descriptor, data):
        nonlocal replacement_written
        if not replacement_written:
            displaced = tmp_path / "displaced-lock"
            lock.path.rename(displaced)
            lock.path.write_text("replacement owner", encoding="utf-8")
            replacement_written = True
        return write(descriptor, data)

    monkeypatch.setattr(os, "write", replace_during_release)
    lock.release()

    assert replacement_written
    assert lock.path.read_text(encoding="utf-8") == "replacement owner"


def test_stale_recovery_never_unlinks_an_interleaved_replacement(tmp_path, monkeypatch):
    destination = tmp_path / "publication"
    lock = tmp_path / ".publication.publication.lock"
    lock.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "destination": str(destination.resolve()),
                "pid": 999_999_999,
                "hostname": socket.gethostname(),
                "created_at": (datetime.now(timezone.utc) - timedelta(hours=25))
                .isoformat()
                .replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )

    def replace_during_liveness_check(pid, signal):
        displaced = tmp_path / "displaced-stale-lock"
        lock.rename(displaced)
        lock.write_text("replacement owner", encoding="utf-8")
        raise ProcessLookupError

    monkeypatch.setattr(os, "kill", replace_during_liveness_check)

    with pytest.raises(PublicationError) as raised:
        make_fixture_publisher().publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.LOCK
    assert lock.read_text(encoding="utf-8") == "replacement owner"


def test_failed_stage_cleanup_never_hides_the_primary_render_error(tmp_path, monkeypatch):
    destination = tmp_path / "publication"
    publisher = make_fixture_publisher()
    publisher.markdown_renderer = RaisingMarkdownRenderer()
    remove_tree = __import__("knowledge_base_publisher").shutil.rmtree

    def fail_stage_cleanup(path, *args, **kwargs):
        if Path(path).name.startswith(".publication.staging-"):
            raise OSError("fixture cleanup failure")
        return remove_tree(path, *args, **kwargs)

    monkeypatch.setattr("knowledge_base_publisher.shutil.rmtree", fail_stage_cleanup)

    with pytest.raises(PublicationError) as raised:
        publisher.publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.RENDER


def test_lock_cleanup_failure_never_hides_the_primary_render_error(tmp_path, monkeypatch):
    destination = tmp_path / "publication"
    publisher = make_fixture_publisher()
    publisher.markdown_renderer = RaisingMarkdownRenderer()
    unlink = Path.unlink

    def fail_lock_unlink(path, *args, **kwargs):
        if path.name.endswith(".publication.lock"):
            raise OSError("fixture lock cleanup failure")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_lock_unlink)

    with pytest.raises(PublicationError) as raised:
        publisher.publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.RENDER


def test_installed_verification_failure_restores_the_existing_publication(tmp_path):
    destination = build_managed_fixture(
        tmp_path / "publication", episodes=(1,), topics=("only-topic",)
    )
    publisher = make_fixture_publisher()
    verify = publisher.verify
    destination_checks = 0
    expected_defects = (PublicationDefect("fixture", "installed verification failure"),)

    def fail_only_installed_root(root):
        nonlocal destination_checks
        if Path(root) == destination:
            destination_checks += 1
        if destination_checks == 3:
            return PublicationVerification(
                PublicationMode.MANAGED,
                expected_defects,
            )
        return verify(root)

    publisher.verify = fail_only_installed_root
    before = snapshot_bytes(destination)

    with pytest.raises(PublicationError) as raised:
        publisher.publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.COMMIT
    assert raised.value.defects == expected_defects
    assert snapshot_bytes(destination) == before
    assert no_sibling_staging_or_backup(destination)


def test_backup_cleanup_failure_restores_the_existing_publication(tmp_path, monkeypatch):
    destination = build_managed_fixture(
        tmp_path / "publication", episodes=(1,), topics=("only-topic",)
    )
    publisher = make_fixture_publisher()
    remove_tree = __import__("knowledge_base_publisher").shutil.rmtree

    def fail_backup_cleanup(path, *args, **kwargs):
        if Path(path).name.startswith(".publication.backup-"):
            (Path(path) / "README.md").unlink()
            raise OSError("fixture backup cleanup failure")
        return remove_tree(path, *args, **kwargs)

    monkeypatch.setattr("knowledge_base_publisher.shutil.rmtree", fail_backup_cleanup)
    before = snapshot_bytes(destination)

    with pytest.raises(PublicationError) as raised:
        publisher.publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.COMMIT
    assert snapshot_bytes(destination) == before


def test_partial_recovery_copy_failure_restores_from_the_intact_backup(tmp_path, monkeypatch):
    destination = build_managed_fixture(
        tmp_path / "publication", episodes=(1,), topics=("only-topic",)
    )
    publisher = make_fixture_publisher()
    copytree = __import__("knowledge_base_publisher").shutil.copytree

    def partially_copy_then_fail(source, target, *args, **kwargs):
        copytree(source, target, *args, **kwargs)
        (Path(target) / "README.md").unlink()
        raise OSError("fixture recovery copy failure")

    monkeypatch.setattr("knowledge_base_publisher.shutil.copytree", partially_copy_then_fail)
    before = snapshot_bytes(destination)

    with pytest.raises(PublicationError) as raised:
        publisher.publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.COMMIT
    assert snapshot_bytes(destination) == before


def test_recovery_cleanup_failure_is_post_commit_garbage_collection(tmp_path, monkeypatch, caplog):
    destination = build_managed_fixture(
        tmp_path / "publication", episodes=(1,), topics=("only-topic",)
    )
    publisher = make_fixture_publisher(episode_numbers=(1, 2))
    remove_tree = __import__("knowledge_base_publisher").shutil.rmtree

    def partially_remove_recovery_then_fail(path, *args, **kwargs):
        if Path(path).name.startswith(".publication.recovery-"):
            (Path(path) / "README.md").unlink()
            raise OSError("fixture recovery cleanup failure")
        return remove_tree(path, *args, **kwargs)

    monkeypatch.setattr(
        "knowledge_base_publisher.shutil.rmtree",
        partially_remove_recovery_then_fail,
    )
    caplog.set_level(logging.WARNING, logger="knowledge_base_publisher")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        manifest = publisher.publish(PublicationRequest(destination))

    assert manifest.source_episodes == (1, 2)
    assert publisher.verify(destination).is_valid
    residuals = list(tmp_path.glob(".publication.recovery-*"))
    assert len(residuals) == 1
    assert not (residuals[0] / "README.md").exists()
    assert str(residuals[0]) in caplog.text


def test_publish_revalidates_destination_ownership_under_the_lock(tmp_path):
    destination = tmp_path / "publication"
    publisher = make_fixture_publisher()
    publisher.markdown_renderer = DestinationMutatingMarkdownRenderer(destination)

    with pytest.raises(PublicationError) as raised:
        publisher.publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.OWNERSHIP
    assert snapshot_bytes(destination) == {"personal.txt": b"do not own"}
    assert no_sibling_staging_or_backup(destination)


def test_synthesis_failure_preserves_the_existing_publication(tmp_path):
    destination = build_managed_fixture(
        tmp_path / "publication", episodes=(1,), topics=("only-topic",)
    )
    publisher = KnowledgeBasePublisher(
        episode_synthesizer=RaisingEpisodeSynthesizer(),
        topic_catalog=(
            TopicDefinition(
                slug="only-topic",
                title="Only topic",
                description="Fixture topic.",
                category="fixture",
                keywords=("Only topic",),
            ),
        ),
    )
    before = snapshot_bytes(destination)

    with pytest.raises(PublicationError) as raised:
        publisher.publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.SYNTHESIS
    assert snapshot_bytes(destination) == before
    assert no_sibling_staging_or_backup(destination)


def test_render_failure_preserves_the_existing_publication(tmp_path):
    destination = build_managed_fixture(
        tmp_path / "publication", episodes=(1,), topics=("only-topic",)
    )
    publisher = make_fixture_publisher()
    publisher.markdown_renderer = RaisingMarkdownRenderer()
    before = snapshot_bytes(destination)

    with pytest.raises(PublicationError) as raised:
        publisher.publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.RENDER
    assert snapshot_bytes(destination) == before
    assert no_sibling_staging_or_backup(destination)


def test_manifest_failure_preserves_the_existing_publication(tmp_path, monkeypatch):
    destination = build_managed_fixture(
        tmp_path / "publication", episodes=(1,), topics=("only-topic",)
    )
    publisher = make_fixture_publisher()
    write_text = Path.write_text

    def fail_staged_manifest(path, *args, **kwargs):
        if path.name == "publication-manifest.json" and path.parent.name.startswith(
            ".publication.staging-"
        ):
            raise OSError("fixture Manifest write failure")
        return write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_staged_manifest)
    before = snapshot_bytes(destination)

    with pytest.raises(PublicationError) as raised:
        publisher.publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.MANIFEST
    assert snapshot_bytes(destination) == before
    assert no_sibling_staging_or_backup(destination)


def test_verification_failure_preserves_the_existing_publication(tmp_path):
    destination = build_managed_fixture(
        tmp_path / "publication", episodes=(1,), topics=("only-topic",)
    )
    publisher = make_fixture_publisher()
    publisher.markdown_renderer = BrokenLinkMarkdownRenderer()
    before = snapshot_bytes(destination)

    with pytest.raises(PublicationError) as raised:
        publisher.publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.VERIFY
    assert raised.value.defects
    assert snapshot_bytes(destination) == before
    assert no_sibling_staging_or_backup(destination)


def test_install_failure_restores_the_existing_publication(tmp_path, monkeypatch):
    destination = build_managed_fixture(
        tmp_path / "publication", episodes=(1,), topics=("only-topic",)
    )
    publisher = make_fixture_publisher()
    replace = os.replace

    def fail_stage_install(source, target):
        if Path(source).name.startswith(".publication.staging-"):
            raise OSError("fixture install failure")
        return replace(source, target)

    monkeypatch.setattr(os, "replace", fail_stage_install)
    before = snapshot_bytes(destination)

    with pytest.raises(PublicationError) as raised:
        publisher.publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.COMMIT
    assert snapshot_bytes(destination) == before
    assert no_sibling_staging_or_backup(destination)


@pytest.mark.parametrize("keep_failed_staging", (False, True))
def test_failed_render_retains_staging_only_when_requested(tmp_path, keep_failed_staging):
    destination = build_managed_fixture(
        tmp_path / "publication", episodes=(1,), topics=("only-topic",)
    )
    publisher = make_fixture_publisher()
    publisher.markdown_renderer = RaisingMarkdownRenderer()
    before = snapshot_bytes(destination)

    with pytest.raises(PublicationError) as raised:
        publisher.publish(
            PublicationRequest(destination, keep_failed_staging=keep_failed_staging)
        )

    staging = raised.value.staging_path
    if keep_failed_staging:
        assert staging is not None and staging.exists()
        assert staging.parent == destination.parent
        assert staging != destination
    else:
        assert staging is None or not staging.exists()
    assert snapshot_bytes(destination) == before


@pytest.mark.parametrize("target_kind", ("filesystem-root", "home", "repository", "symlink", "unknown"))
def test_publish_rejects_unowned_destinations_before_lock_or_staging(tmp_path, target_kind):
    if target_kind == "filesystem-root":
        destination = Path("/")
    elif target_kind == "home":
        destination = Path.home()
    elif target_kind == "repository":
        destination = Path(__file__).resolve().parent.parent
    elif target_kind == "symlink":
        owned = tmp_path / "owned"
        owned.mkdir()
        destination = tmp_path / "linked"
        destination.symlink_to(owned, target_is_directory=True)
    else:
        destination = tmp_path / "unknown"
        destination.mkdir()
        (destination / "personal.txt").write_text("do not own", encoding="utf-8")
    synthesizer = FixtureEpisodeSynthesizer((1,))
    publisher = KnowledgeBasePublisher(episode_synthesizer=synthesizer)
    before = (
        os.readlink(destination)
        if destination.is_symlink()
        else snapshot_bytes(destination)
        if destination.is_dir() and destination.parent == tmp_path
        else None
    )

    with pytest.raises(PublicationError) as raised:
        publisher.publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.OWNERSHIP
    assert synthesizer.call_count == 0
    assert (
        os.readlink(destination)
        if destination.is_symlink()
        else snapshot_bytes(destination)
        if destination.is_dir() and destination.parent == tmp_path
        else None
    ) == before
    assert not (destination.parent / f".{destination.name}.publication.lock").exists()


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
    assert list(tmp_path.glob(".publication.recovery-*")) == []


@pytest.mark.parametrize("max_workers", (0, -1))
def test_publish_rejects_non_positive_workers_before_writing(tmp_path, max_workers):
    publisher = make_fixture_publisher(
        episode_numbers=(1,),
        topic_slugs=("only-topic",),
    )
    destination = tmp_path / "publication"

    with pytest.raises(PublicationError, match="positive integer") as raised:
        publisher.publish(
            PublicationRequest(destination=destination, max_workers=max_workers)
        )

    assert raised.value.phase is PublicationPhase.OWNERSHIP
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


def test_publish_rejects_the_workspace_root_before_synthesis():
    synthesizer = FixtureEpisodeSynthesizer((1,))
    publisher = KnowledgeBasePublisher(episode_synthesizer=synthesizer)
    workspace_root = Path(__file__).resolve().parent.parent

    with pytest.raises(PublicationError, match="protected directory") as raised:
        publisher.publish(PublicationRequest(destination=workspace_root))

    assert raised.value.phase is PublicationPhase.OWNERSHIP
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

    assert list(tmp_path.glob(".publication.staging-*")) == []
    assert list(tmp_path.glob(".publication.backup-*")) == []


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

    assert list(tmp_path.glob(".publication.staging-*")) == []
    assert list(tmp_path.glob(".publication.backup-*")) == []


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
