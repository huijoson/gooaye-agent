"""Filesystem contract for staged snapshot replacement on the /mnt/c mount."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

import episode_source_repository as repository_module
from domain import EpisodeSourceSnapshot
from episode_source_repository import EpisodeSourceRepository, SnapshotCommitError


REPO_ROOT = Path(__file__).resolve().parent.parent


def make_snapshot(marker: str) -> EpisodeSourceSnapshot:
    return EpisodeSourceSnapshot(
        number=691,
        youtube_id="J-e9oxqLzpc",
        youtube_title="EP691 | birthday",
        published_at="2026-08-26T08:23:12+00:00",
        duration_seconds=2995,
        archive_filename="EP691_contract.md",
        display_title="Filesystem contract",
        archive_date="2026-08-26",
        summary="Verify staged directory replacement on the repository filesystem.",
        transcript="# EP691 Filesystem contract\n\n" + marker * 1200,
        source_urls={
            "youtube_metadata": "https://example.test/youtube.xml",
            "duration_metadata": "https://example.test/soundon.xml",
            "archive_index": "https://example.test/episodes.json",
            "transcript": "https://example.test/EP691.md",
        },
        fetched_at=datetime(2026, 8, 28, tzinfo=UTC).isoformat(),
    )


def test_mnt_c_staging_force_and_rollback_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert str(REPO_ROOT).startswith("/mnt/c/")
    with TemporaryDirectory(
        prefix="episode-source-filesystem-contract-",
        dir=REPO_ROOT / ".work",
    ) as temporary_directory:
        root = Path(temporary_directory)
        repository = EpisodeSourceRepository(
            snapshot_root=root / "episode-sources",
            legacy_channel_path=root / "channel.json",
            legacy_archive_path=root / "episodes.json",
            legacy_transcript_dir=root / "full-transcripts",
        )

        assert repository.commit(make_snapshot("甲")) == "created"
        assert repository.commit(make_snapshot("甲")) == "unchanged"
        assert repository.commit(make_snapshot("乙"), force=True) == "updated"
        assert repository.verify(691).is_valid
        assert "乙" in repository.load_transcript(691)

        real_replace = repository_module.os.replace
        replace_calls = 0

        def fail_second_replace(source: Path, target: Path) -> None:
            nonlocal replace_calls
            replace_calls += 1
            if replace_calls == 2:
                raise OSError("injected /mnt/c install failure")
            real_replace(source, target)

        monkeypatch.setattr(repository_module.os, "replace", fail_second_replace)
        with pytest.raises(SnapshotCommitError, match="injected /mnt/c install failure"):
            repository.commit(make_snapshot("丙"), force=True)

        assert repository.verify(691).is_valid
        assert "乙" in repository.load_transcript(691)
        assert "丙" not in repository.load_transcript(691)
        assert not list(repository.snapshot_root.glob("*.staging"))
        assert not list(repository.snapshot_root.glob("*.backup"))
