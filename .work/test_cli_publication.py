"""CLI contracts for transactional Knowledge Base Publication and Preview output."""

from __future__ import annotations

import os
import subprocess
import sys
from argparse import Namespace
from collections import Counter
from pathlib import Path

import pytest

import cli
from domain import SynthesisSummary
from knowledge_base_publisher import (
    PublicationDefect,
    PublicationError,
    PublicationManifest,
    PublicationMode,
    PublicationPhase,
    PublicationVerification,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


def formal_tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def formal_tree_status() -> str:
    result = subprocess.run(
        ["git", "status", "--short", "--", "gooaye-youtube-notes"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    )
    return result.stdout


@pytest.fixture(scope="module", autouse=True)
def formal_tree_guard():
    """Keep this module hermetic even if a negative command regresses."""
    before = formal_tree_bytes(cli.OUTPUT_DIR)
    status_before = formal_tree_status()
    yield
    assert formal_tree_bytes(cli.OUTPUT_DIR) == before
    assert formal_tree_status() == status_before


def run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, ".work/cli.py", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=os.environ.copy(),
    )


def test_publish_has_no_subset_flags() -> None:
    result = run_cli(["publish", "--help"])

    assert result.returncode == 0
    assert "--output-dir" in result.stdout
    assert "--resolver" in result.stdout
    assert "--workers" in result.stdout
    assert "--episode" not in result.stdout
    assert "--topic" not in result.stdout


def test_verify_has_only_an_output_destination() -> None:
    result = run_cli(["verify", "--help"])

    assert result.returncode == 0
    assert "--output-dir" in result.stdout
    assert "--resolver" not in result.stdout
    assert "--workers" not in result.stdout


def test_preview_requires_an_explicit_isolated_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MustNotConstructSynthesizer:
        def __init__(self) -> None:
            raise AssertionError("unsafe Preview command constructed a writer collaborator")

    monkeypatch.setattr(cli, "EpisodeNoteSynthesizer", MustNotConstructSynthesizer)
    monkeypatch.setattr(sys, "argv", ["cli.py", "synthesize", "--episode", "1"])

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2


def test_topic_preview_requires_an_explicit_isolated_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MustNotConstructSynthesizer:
        def __init__(self) -> None:
            raise AssertionError("unsafe topic Preview command constructed a writer collaborator")

    monkeypatch.setattr(cli, "EpisodeNoteSynthesizer", MustNotConstructSynthesizer)
    monkeypatch.setattr(sys, "argv", ["cli.py", "topics", "--generate"])

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2


class FixturePublisher:
    def __init__(self, verification: PublicationVerification | None = None) -> None:
        self.episode_synthesizer = type("Synthesizer", (), {"quality": object()})()
        self.requests = []
        self.verify_roots = []
        self.verification = verification or PublicationVerification(
            mode=PublicationMode.MANAGED,
            defects=(),
            artifact_count=9,
            episode_count=2,
            topic_count=1,
        )

    def publish(self, request):
        self.requests.append(request)
        return PublicationManifest(
            schema_version=1,
            created_at="2026-08-29T00:00:00Z",
            source_episodes=(1, 2),
            topic_catalog=("fixture",),
            total_chapters=3,
            total_seconds=120,
            artifacts=(),
        )

    def verify(self, root: Path) -> PublicationVerification:
        self.verify_roots.append(root)
        return self.verification


def test_publish_passes_one_selected_resolver_and_reports_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    publisher = FixturePublisher()
    selected = object()
    calls = []
    monkeypatch.setattr(cli, "KnowledgeBasePublisher", lambda: publisher)
    monkeypatch.setattr(
        cli,
        "select_heading_resolver",
        lambda strategy, quality_engine: calls.append((strategy, quality_engine)) or selected,
    )

    destination = tmp_path / "publication"
    cli.cmd_publish(
        Namespace(
            output_dir=destination,
            resolver="deterministic",
            workers=3,
            keep_failed_staging=False,
        )
    )
    output = capsys.readouterr().out

    assert len(calls) == 1
    assert publisher.requests[0].destination == destination
    assert publisher.requests[0].resolver is selected
    assert publisher.requests[0].max_workers == 3
    assert "publish duration:" in output
    assert "commit: OK" in output
    assert "artifacts: 9" in output
    assert "episodes: 2" in output
    assert "topics: 1" in output
    assert "verification: OK" in output
    assert destination in publisher.verify_roots


def test_publish_reports_publication_phase_defects_and_retained_staging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    retained = tmp_path / ".publication.staging-retained"

    class FailingPublisher:
        episode_synthesizer = type("Synthesizer", (), {"quality": object()})()

        def publish(self, request):
            raise PublicationError(
                PublicationPhase.LOCK,
                "destination is locked",
                defects=(PublicationDefect("lock", "held by fixture"),),
                staging_path=retained,
            )

    monkeypatch.setattr(cli, "KnowledgeBasePublisher", FailingPublisher)
    monkeypatch.setattr(cli, "select_heading_resolver", lambda *_: object())

    with pytest.raises(SystemExit, match="1"):
        cli.cmd_publish(
            Namespace(
                output_dir=tmp_path / "publication",
                resolver="composite",
                workers=1,
                keep_failed_staging=True,
            )
        )
    error = capsys.readouterr().err

    assert "phase: lock" in error
    assert "held by fixture" in error
    assert str(retained) in error


def test_verify_reports_counts_and_never_calls_a_writer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    publisher = FixturePublisher()
    monkeypatch.setattr(cli, "KnowledgeBasePublisher", lambda: publisher)

    destination = tmp_path / "publication"
    cli.cmd_verify(Namespace(output_dir=destination))
    output = capsys.readouterr().out

    assert publisher.requests == []
    assert publisher.verify_roots == [destination]
    assert "mode: managed" in output
    assert "artifacts: 9" in output
    assert "episodes: 2" in output
    assert "topics: 1" in output
    assert "defects: 0" in output
    assert "verification: OK" in output


def test_verify_fails_for_unknown_or_defective_destination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    publisher = FixturePublisher(
        PublicationVerification(
            mode=PublicationMode.UNKNOWN,
            defects=(PublicationDefect("ownership", "not a publication"),),
        )
    )
    monkeypatch.setattr(cli, "KnowledgeBasePublisher", lambda: publisher)

    with pytest.raises(SystemExit, match="1"):
        cli.cmd_verify(Namespace(output_dir=tmp_path / "not-publication"))
    error = capsys.readouterr().err

    assert "mode: unknown" in error
    assert "ownership" in error


def test_preview_rejects_formal_symlink_and_nonempty_destinations(tmp_path: Path) -> None:
    formal = cli.OUTPUT_DIR
    with pytest.raises(ValueError, match="formal publication"):
        cli.preview_output_directory(formal)

    populated = tmp_path / "populated-preview"
    populated.mkdir()
    (populated / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="new or empty"):
        cli.preview_output_directory(populated)
    assert (populated / "keep.txt").read_text(encoding="utf-8") == "keep"

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "preview-link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="must not be a symlink"):
        cli.preview_output_directory(link)


def test_synthesize_preview_writes_only_episode_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "preview"

    class PreviewSynthesizer:
        quality = object()

        def synthesize_all(self, **kwargs):
            destination = kwargs["output_dir"]
            (destination / "episodes").mkdir(parents=True)
            (destination / "episodes" / "EP0001.md").write_text("preview", encoding="utf-8")
            return SynthesisSummary(1, 1, 60, Counter({1: 1}), ())

    monkeypatch.setattr(cli, "EpisodeNoteSynthesizer", PreviewSynthesizer)
    monkeypatch.setattr(cli, "select_heading_resolver", lambda *_: object())

    cli.cmd_synthesize(
        Namespace(
            output_dir=output_dir,
            out_dir=None,
            resolver="composite",
            workers=1,
            dry_run=False,
            episode=1,
            episodes=None,
        )
    )

    assert (output_dir / "episodes" / "EP0001.md").is_file()
    assert not (output_dir / "publication-manifest.json").exists()
    assert not (output_dir / "README.md").exists()
    assert not (output_dir / "_index.md").exists()


def test_topic_preview_uses_the_in_memory_summary_notes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "topic-preview"
    notes = (object(),)
    summary = SynthesisSummary(1, 1, 60, Counter({1: 1}), notes)

    class PreviewSynthesizer:
        def synthesize_notes(self):
            return summary

    class PreviewTopics:
        received_notes = None

        def synthesize_and_save_all(self, input_notes, output_dir, topics):
            type(self).received_notes = input_notes
            output_dir.mkdir(parents=True)
            (output_dir / "fixture.md").write_text("preview", encoding="utf-8")
            return [output_dir / "fixture.md"]

    import topic_synthesizer

    monkeypatch.setattr(cli, "EpisodeNoteSynthesizer", PreviewSynthesizer)
    monkeypatch.setattr(topic_synthesizer, "TopicGuideSynthesizer", PreviewTopics)
    monkeypatch.setattr(
        topic_synthesizer,
        "load_all_notes_from_dir",
        lambda *_: (_ for _ in ()).throw(AssertionError("must not parse formal Markdown")),
    )

    cli.cmd_topics(
        Namespace(
            generate=True,
            list=False,
            topic="ai-hardware-and-semiconductor",
            output_dir=output_dir,
            out_dir=None,
            audit=False,
        )
    )

    assert PreviewTopics.received_notes is notes
    assert (output_dir / "topics" / "fixture.md").is_file()
    assert not (output_dir / "README.md").exists()
    assert not (output_dir / "_index.md").exists()
    assert not (output_dir / "publication-manifest.json").exists()
