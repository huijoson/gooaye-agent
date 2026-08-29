from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

import episode_source_repository as repository_module
from episode_source_repository import (
    EpisodeSourceRepository,
    EpisodeSourceSnapshot,
    InvalidSnapshotError,
    SnapshotCommitError,
    SnapshotConflictError,
)


def make_repository(root: Path) -> EpisodeSourceRepository:
    return EpisodeSourceRepository(
        snapshot_root=root / "episode-sources",
        legacy_channel_path=root / "channel.json",
        legacy_archive_path=root / "episodes.json",
        legacy_transcript_dir=root / "full-transcripts",
    )


def make_snapshot(number: int = 691, transcript: str | None = None) -> EpisodeSourceSnapshot:
    return EpisodeSourceSnapshot(
        number=number,
        youtube_id="J-e9oxqLzpc",
        youtube_title="EP691 | 🎂",
        published_at="2026-08-26T08:23:12+00:00",
        duration_seconds=2995,
        archive_filename="EP691_北海道敲門驚魂與人人一個Jarvis.md",
        display_title="北海道敲門驚魂與人人一個Jarvis",
        archive_date="2026-08-26",
        summary="北海道旅行、AI 工具與投資判斷之間的分工。",
        transcript=transcript or "# EP691 北海道敲門驚魂與人人一個Jarvis\n\n" + "這是完整逐字稿內容。" * 200,
        source_urls={
            "youtube_metadata": "https://www.youtube.com/feeds/videos.xml?channel_id=test",
            "duration_metadata": "https://feeds.soundon.fm/test.xml",
            "archive_index": "https://whatmkreallysaid.com/episodes.json",
            "transcript": "https://whatmkreallysaid.com/episodes/EP691.md",
        },
        fetched_at=datetime(2026, 8, 28, 0, 0, tzinfo=UTC).isoformat(),
    )


def test_commit_creates_a_verified_self_contained_snapshot(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)

    result = repository.commit(make_snapshot())

    assert result == "created"
    assert repository.verify(691).is_valid
    assert (tmp_path / "episode-sources/EP0691/snapshot.json").is_file()
    assert (tmp_path / "episode-sources/EP0691/transcript.md").is_file()


def test_verify_rejects_a_tampered_transcript(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository.commit(make_snapshot())
    transcript_path = tmp_path / "episode-sources/EP0691/transcript.md"
    transcript_path.write_text("tampered", encoding="utf-8")

    report = repository.verify(691)

    assert not report.is_valid
    assert any("sha256" in defect for defect in report.defects)


def test_verify_rejects_tampered_manifest_content(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository.commit(make_snapshot())
    manifest_path = tmp_path / "episode-sources/EP0691/snapshot.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["archive"]["summary"] = "被竄改的摘要"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = repository.verify(691)

    assert not report.is_valid
    assert any("content_sha256" in defect for defect in report.defects)


def test_verify_rejects_self_consistent_but_semantically_invalid_manifest(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)
    repository.commit(make_snapshot())
    snapshot_dir = tmp_path / "episode-sources/EP0691"
    manifest_path = snapshot_dir / "snapshot.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["official"]["youtube_id"] = "not-a-youtube-id"
    manifest["official"]["duration_seconds"] = 0
    manifest["archive"]["filename"] = "."
    manifest["archive"]["date"] = "not-a-date"
    manifest["provenance"]["source_urls"] = {"youtube_metadata": ""}
    manifest["provenance"]["fetched_at"] = "not-a-time"
    content = {
        "official": manifest["official"],
        "archive": manifest["archive"],
        "transcript": manifest["transcript"],
    }
    manifest["content_sha256"] = repository_module._sha256(
        json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = repository.verify(691)

    assert not report.is_valid
    assert any("youtube_id" in defect for defect in report.defects)
    assert any("duration_seconds" in defect for defect in report.defects)
    assert any("archive_filename" in defect for defect in report.defects)
    assert any("archive_date" in defect for defect in report.defects)
    assert any("source_urls" in defect for defect in report.defects)
    assert any("fetched_at" in defect for defect in report.defects)


def test_verify_rejects_invalid_field_types_without_crashing(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository.commit(make_snapshot())
    manifest_path = tmp_path / "episode-sources/EP0691/snapshot.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["official"]["published_at"] = []
    manifest["archive"]["summary"] = 1
    manifest["provenance"]["source_urls"] = []
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = repository.verify(691)

    assert not report.is_valid
    assert any("official schema" in defect for defect in report.defects)
    assert any("archive schema" in defect for defect in report.defects)
    assert any("provenance schema" in defect for defect in report.defects)


def test_identical_snapshot_is_unchanged_without_rewriting_files(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    snapshot = make_snapshot()
    repository.commit(snapshot)
    manifest_path = tmp_path / "episode-sources/EP0691/snapshot.json"
    before = manifest_path.read_bytes()

    result = repository.commit(snapshot)

    assert result == "unchanged"
    assert manifest_path.read_bytes() == before


def test_changed_snapshot_requires_force(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository.commit(make_snapshot(transcript="# EP691\n\n" + "甲" * 1000))

    with pytest.raises(SnapshotConflictError):
        repository.commit(make_snapshot(transcript="# EP691\n\n" + "乙" * 1000))


def test_force_replaces_the_complete_directory(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository.commit(make_snapshot(transcript="# EP691\n\n" + "甲" * 1000))

    result = repository.commit(
        make_snapshot(transcript="# EP691\n\n" + "乙" * 1000),
        force=True,
    )

    assert result == "updated"
    assert "乙" in repository.load_transcript(691)
    assert "甲" not in repository.load_transcript(691)
    assert repository.verify(691).is_valid


def test_force_failure_restores_the_previous_complete_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = make_repository(tmp_path)
    repository.commit(make_snapshot(transcript="# EP691\n\n" + "甲" * 1000))
    real_replace = repository_module.os.replace
    call_count = 0

    def fail_install(source: Path, target: Path) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("injected install failure")
        real_replace(source, target)

    monkeypatch.setattr(repository_module.os, "replace", fail_install)

    with pytest.raises(SnapshotCommitError, match="injected install failure"):
        repository.commit(
            make_snapshot(transcript="# EP691\n\n" + "乙" * 1000),
            force=True,
        )

    assert "甲" in repository.load_transcript(691)
    assert repository.verify(691).is_valid
    assert not list((tmp_path / "episode-sources").glob("*.backup"))


def test_mkdir_failure_is_a_snapshot_commit_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = make_repository(tmp_path)
    real_mkdir = Path.mkdir

    def fail_snapshot_root_mkdir(path: Path, *args: object, **kwargs: object) -> None:
        if path == repository.snapshot_root:
            raise OSError("injected mkdir failure")
        real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_snapshot_root_mkdir)

    with pytest.raises(SnapshotCommitError, match="injected mkdir failure"):
        repository.commit(make_snapshot())


def test_mkdtemp_failure_is_a_snapshot_commit_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = make_repository(tmp_path)

    def fail_mkdtemp(*args: object, **kwargs: object) -> str:
        raise OSError("injected mkdtemp failure")

    monkeypatch.setattr(repository_module.tempfile, "mkdtemp", fail_mkdtemp)

    with pytest.raises(SnapshotCommitError, match="injected mkdtemp failure"):
        repository.commit(make_snapshot())


def test_staging_write_failure_is_a_snapshot_commit_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = make_repository(tmp_path)
    real_write_bytes = Path.write_bytes

    def fail_staging_write(path: Path, data: bytes) -> int:
        if path.name == "transcript.md" and path.parent.name.endswith(".staging"):
            raise OSError("injected staging write failure")
        return real_write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_staging_write)

    with pytest.raises(SnapshotCommitError, match="injected staging write failure"):
        repository.commit(make_snapshot())


def test_cleanup_failure_is_a_snapshot_commit_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = make_repository(tmp_path)
    repository.commit(make_snapshot(transcript="# EP691\n\n" + "甲" * 1000))
    real_rmtree = repository_module.shutil.rmtree

    def fail_backup_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        if path.name.endswith(".backup"):
            raise OSError("injected cleanup failure")
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(repository_module.shutil, "rmtree", fail_backup_cleanup)

    with pytest.raises(SnapshotCommitError, match="injected cleanup failure"):
        repository.commit(
            make_snapshot(transcript="# EP691\n\n" + "乙" * 1000),
            force=True,
        )


def test_cleanup_failure_does_not_mask_primary_commit_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = make_repository(tmp_path)
    repository.commit(make_snapshot(transcript="# EP691\n\n" + "甲" * 1000))
    real_replace = repository_module.os.replace
    replace_calls = 0

    def fail_install(source: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("injected primary install failure")
        real_replace(source, target)

    def fail_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        if path.name.endswith(".staging"):
            raise OSError("injected cleanup failure")
        repository_module.shutil.rmtree(path, *args, **kwargs)

    monkeypatch.setattr(repository_module.os, "replace", fail_install)
    monkeypatch.setattr(repository_module.shutil, "rmtree", fail_cleanup)

    with pytest.raises(SnapshotCommitError, match="injected primary install failure") as error:
        repository.commit(make_snapshot(transcript="# EP691\n\n" + "乙" * 1000), force=True)

    assert "cleanup failure" not in str(error.value)
    assert "甲" in repository.load_transcript(691)
    assert repository.verify(691).is_valid


def test_invalid_snapshot_never_creates_a_target(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    invalid = make_snapshot(transcript="<html>not a transcript</html>")

    with pytest.raises(InvalidSnapshotError):
        repository.commit(invalid)

    assert not (tmp_path / "episode-sources/EP0691").exists()


def test_repository_merges_legacy_and_normalized_sources(tmp_path: Path) -> None:
    channel_path = tmp_path / "channel.json"
    archive_path = tmp_path / "episodes.json"
    transcript_dir = tmp_path / "full-transcripts"
    transcript_dir.mkdir()
    channel_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "xLS-2whm8Aw",
                        "title": "EP1 | 武漢肺炎",
                        "duration": 1423,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    archive_path.write_text(
        json.dumps(
            [
                {
                    "number": 1,
                    "filename": "EP1.md",
                    "display_title": "歐洲疫情與股市崩跌",
                    "date": "2020-02-27",
                    "summary": "歐洲疫情擴散與全球市場恐慌。",
                }
            ]
        ),
        encoding="utf-8",
    )
    (transcript_dir / "EP0001.md").write_text("# EP1\n\n完整逐字稿", encoding="utf-8")
    repository = EpisodeSourceRepository(
        snapshot_root=tmp_path / "episode-sources",
        legacy_channel_path=channel_path,
        legacy_archive_path=archive_path,
        legacy_transcript_dir=transcript_dir,
    )

    assert repository.episode_numbers == [1]
    assert repository.get_metadata(1).youtube_id == "xLS-2whm8Aw"
    assert repository.load_transcript(1).startswith("# EP1")

    repository.commit(make_snapshot())

    assert repository.episode_numbers == [1, 691]
    assert repository.get_metadata(691).youtube_id == "J-e9oxqLzpc"
    assert repository.load_transcript(691).startswith("# EP691")


def test_legacy_metadata_keeps_youtube_sample_date_fallback(tmp_path: Path) -> None:
    channel_path = tmp_path / "channel.json"
    archive_path = tmp_path / "episodes.json"
    transcript_dir = tmp_path / "full-transcripts"
    samples_dir = tmp_path / "samples"
    transcript_dir.mkdir()
    samples_dir.mkdir()
    channel_path.write_text(
        json.dumps(
            {"entries": [{"id": "xLS-2whm8Aw", "title": "EP1 | 舊集", "duration": 60}]}
        ),
        encoding="utf-8",
    )
    archive_path.write_text(
        json.dumps(
            [{"number": 1, "filename": "EP1.md", "summary": "舊集摘要", "title": "舊集"}]
        ),
        encoding="utf-8",
    )
    (samples_dir / "xLS-2whm8Aw.metadata.json").write_text(
        json.dumps({"upload_date": "20200227"}),
        encoding="utf-8",
    )
    repository = make_repository(tmp_path)

    metadata = repository.get_metadata(1)

    assert metadata.date == "2020-02-27"
    assert metadata.date_source == "youtube_metadata"
