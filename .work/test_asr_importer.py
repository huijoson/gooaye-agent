from dataclasses import replace
import json
from pathlib import Path

import pytest

from asr_importer import build_asr_snapshot
from cold_transcript_exporter import format_cold_transcript
from domain import EpisodeNote
from episode_source_repository import InvalidSnapshotError, SnapshotConflictError
from test_episode_source_repository import make_repository, make_snapshot


def asr_snapshot():
    legacy = make_snapshot()
    return replace(
        legacy,
        source_urls={
            "youtube_metadata": legacy.source_urls["youtube_metadata"],
            "duration_metadata": legacy.source_urls["duration_metadata"],
            "audio": "https://example.org/audio.mp3",
            "transcript": "file:///local/transcript.md",
        },
        transcription={
            "engine": "mlx-whisper", "model": "whisper-large-v3-turbo",
            "audio_url": "https://example.org/audio.mp3", "audio_sha256": "a" * 64,
        },
    )


def test_asr_roundtrip_discloses_source_without_fictitious_third_party(tmp_path):
    repository = make_repository(tmp_path)
    snapshot = asr_snapshot()
    repository.commit(snapshot)
    assert repository.verify(691).is_valid
    metadata = repository.get_metadata(691)
    assert metadata.transcription == snapshot.transcription
    assert metadata.archive_url == ""
    assert metadata.date_source == "official_metadata"
    cold = format_cold_transcript(metadata, snapshot.transcript)
    note = EpisodeNote(metadata, ()).render_markdown()
    for rendered in (cold, note):
        assert "whatmkreallysaid.com" not in rendered
        assert "未經逐句人工校對" in rendered
        assert "https://example.org/audio.mp3" in rendered
    assert 'source: "official_audio_asr"' in cold
    assert 'transcription_model: "whisper-large-v3-turbo"' in cold


@pytest.mark.parametrize("field,value", [("model", ""), ("audio_sha256", "invalid"), ("audio_url", "https://different.org/audio.mp3")])
def test_invalid_asr_provenance_is_rejected(tmp_path, field, value):
    snapshot = asr_snapshot()
    with pytest.raises(InvalidSnapshotError):
        make_repository(tmp_path).commit(replace(snapshot, transcription={**snapshot.transcription, field: value}))
    assert not (tmp_path / "episode-sources").exists()


def test_non_mapping_asr_provenance_is_rejected_at_boundary(tmp_path):
    with pytest.raises(InvalidSnapshotError):
        make_repository(tmp_path).commit(replace(asr_snapshot(), transcription=["bad"]))


def test_model_change_is_a_content_conflict_and_tampering_is_detected(tmp_path):
    repository = make_repository(tmp_path)
    snapshot = asr_snapshot()
    repository.commit(snapshot)
    with pytest.raises(SnapshotConflictError):
        repository.commit(replace(snapshot, transcription={**snapshot.transcription, "model": "different"}))
    path = tmp_path / "episode-sources/EP0691/snapshot.json"
    manifest = json.loads(path.read_text())
    manifest["transcript"]["transcription"]["model"] = "tampered"
    path.write_text(json.dumps(manifest))
    assert not repository.verify(691).is_valid


def test_force_corrects_asr_provenance_without_changing_transcript(tmp_path):
    repository = make_repository(tmp_path)
    snapshot = asr_snapshot()
    repository.commit(snapshot)
    corrected = replace(snapshot, source_urls={**snapshot.source_urls, "transcript": snapshot.source_urls["audio"]})
    assert repository.commit(corrected, force=True) == "updated"
    assert repository.verify(691).is_valid
    manifest = json.loads((tmp_path / "episode-sources/EP0691/snapshot.json").read_text())
    assert manifest["provenance"]["source_urls"]["transcript"] == snapshot.source_urls["audio"]


def test_builder_hashes_real_audio_and_preserves_text(tmp_path: Path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio fixture")
    transcript = tmp_path / "transcript.md"
    transcript.write_text(make_snapshot().transcript)
    snapshot = build_asr_snapshot(
        number=691, youtube_id="J-e9oxqLzpc", youtube_title="EP691 | Official",
        published_at="2026-08-26T08:23:12+00:00", duration_seconds=2995,
        transcript_path=transcript, audio_path=audio, audio_url="https://example.org/audio.mp3",
        youtube_metadata_url="https://youtube.com/feed", duration_metadata_url="https://feeds.soundon.fm/test.xml",
        engine="mlx-whisper", model="whisper-large-v3-turbo", fetched_at="2026-09-24T00:00:00+00:00",
        summary="逐字稿檢索提示", extra_provenance={"model_revision": "revision"},
    )
    repository = make_repository(tmp_path)
    repository.commit(snapshot)
    assert repository.load_transcript(691) == transcript.read_text()
    assert snapshot.display_title == "EP691 | Official"
    assert snapshot.transcription["model_revision"] == "revision"
    assert len(snapshot.transcription["audio_sha256"]) == 64
    assert snapshot.source_urls["transcript"] == "https://example.org/audio.mp3"


def test_asr_note_and_publication_describe_mixed_sources(tmp_path):
    from collections import Counter
    from domain import SynthesisSummary
    from markdown_renderer import MarkdownRenderer

    repository = make_repository(tmp_path)
    repository.commit(asr_snapshot())
    note = EpisodeNote(repository.get_metadata(691), ())
    rendered = note.render_markdown()
    assert 'source: "official_audio_asr"' in rendered
    assert 'transcription_model: "whisper-large-v3-turbo"' in rendered
    summary = SynthesisSummary(1, 0, 2995, Counter(), (note,))
    readme = MarkdownRenderer.render_readme([note], summary)
    assert "1 集官方節目音訊的自動語音轉錄" in readme
    assert "未經逐句人工校對" in readme
    assert "自動轉錄集數則使用官方節目標題" in readme
