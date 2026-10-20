"""Build an explicit local-ASR source snapshot from official episode metadata."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Mapping

from domain import EpisodeSourceSnapshot


def build_asr_snapshot(
    *,
    number: int,
    youtube_id: str,
    youtube_title: str,
    published_at: str,
    duration_seconds: int,
    transcript_path: Path,
    audio_path: Path,
    audio_url: str,
    youtube_metadata_url: str,
    duration_metadata_url: str,
    engine: str,
    model: str,
    fetched_at: str,
    summary: str,
    extra_provenance: Mapping[str, str] | None = None,
) -> EpisodeSourceSnapshot:
    """Preserve transcript bytes and hash audio; repository.commit validates/install it.

    `summary` is a retrieval hint derived from this transcript, not an archive
    summary. Extra provenance may record revision, language, or postprocessing.
    """
    with audio_path.open("rb") as audio_file:
        audio_sha256 = hashlib.file_digest(audio_file, "sha256").hexdigest()
    transcription = dict(extra_provenance or {})
    transcription.update(
        engine=engine, model=model, audio_url=audio_url, audio_sha256=audio_sha256
    )
    return EpisodeSourceSnapshot(
        number=number,
        youtube_id=youtube_id,
        youtube_title=youtube_title,
        published_at=published_at,
        duration_seconds=duration_seconds,
        archive_filename=f"EP{number:04d}.md",
        display_title=youtube_title,
        archive_date=datetime.fromisoformat(published_at.replace("Z", "+00:00")).date().isoformat(),
        summary=summary,
        transcript=transcript_path.read_text(encoding="utf-8"),
        source_urls={
            "youtube_metadata": youtube_metadata_url,
            "duration_metadata": duration_metadata_url,
            "audio": audio_url,
            "transcript": audio_url,
        },
        fetched_at=fetched_at,
        transcription=transcription,
    )
