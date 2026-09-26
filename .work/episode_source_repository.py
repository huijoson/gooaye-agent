"""Persistence boundary for legacy and normalized episode source data."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote, urlparse
from uuid import uuid4

from domain import (
    EpisodeMetadata,
    EpisodeSourceSnapshot,
    EpisodeSourceVerification,
    format_duration,
)


SCHEMA_VERSION = 1
TRANSCRIPT_FILENAME = "transcript.md"
MANIFEST_FILENAME = "snapshot.json"
REQUIRED_SOURCE_URLS = frozenset(
    {"youtube_metadata", "duration_metadata", "archive_index", "transcript"}
)
MIN_TRANSCRIPT_BYTES = 1000


class EpisodeSourceError(RuntimeError):
    """Base error for episode source persistence."""


class InvalidSnapshotError(EpisodeSourceError):
    """Raised when an in-memory snapshot violates the source contract."""


class SnapshotConflictError(EpisodeSourceError):
    """Raised when changed source data would overwrite an existing snapshot."""


class SnapshotCommitError(EpisodeSourceError):
    """Raised when a staged snapshot cannot cross the commit boundary safely."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class EpisodeSourceRepository:
    """Own normalized source snapshots while retaining legacy read compatibility."""

    def __init__(
        self,
        snapshot_root: Path,
        legacy_channel_path: Path,
        legacy_archive_path: Path,
        legacy_transcript_dir: Path,
        archive_base_url: str = "https://whatmkreallysaid.com/",
    ) -> None:
        self.snapshot_root = Path(snapshot_root)
        self.legacy_channel_path = Path(legacy_channel_path)
        self.legacy_archive_path = Path(legacy_archive_path)
        self.legacy_transcript_dir = Path(legacy_transcript_dir)
        self.archive_base_url = archive_base_url.rstrip("/") + "/"
        self._legacy_channel_entries: dict[int, dict] | None = None
        self._legacy_archive_entries: dict[int, dict] | None = None

    @staticmethod
    def _episode_dir_name(number: int) -> str:
        return f"EP{number:04d}"

    def _episode_dir(self, number: int) -> Path:
        return self.snapshot_root / self._episode_dir_name(number)

    @staticmethod
    def is_safe_archive_filename(filename: str) -> bool:
        """Return whether an archive filename can safely form one URL segment."""
        return (
            bool(filename)
            and filename not in {".", ".."}
            and Path(filename).name == filename
            and "\\" not in filename
        )

    @staticmethod
    def _is_absolute_url(value: object) -> bool:
        if not isinstance(value, str) or not value.strip():
            return False
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https", "file"} and bool(
            parsed.netloc or parsed.scheme == "file"
        )

    @staticmethod
    def _validate_snapshot(snapshot: EpisodeSourceSnapshot) -> None:
        defects: list[str] = []
        if not isinstance(snapshot.number, int) or isinstance(snapshot.number, bool):
            defects.append("episode number must be an integer")
        elif snapshot.number <= 0:
            defects.append("episode number must be positive")
        if not isinstance(snapshot.youtube_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{11}", snapshot.youtube_id
        ):
            defects.append("youtube_id must be an 11-character video ID")
        if not isinstance(snapshot.youtube_title, str) or not snapshot.youtube_title.strip():
            defects.append("youtube_title is required")
        if (
            not isinstance(snapshot.duration_seconds, int)
            or isinstance(snapshot.duration_seconds, bool)
            or snapshot.duration_seconds <= 0
        ):
            defects.append("duration_seconds must be positive")
        if not isinstance(snapshot.display_title, str) or not snapshot.display_title.strip():
            defects.append("display_title is required")
        if not isinstance(snapshot.summary, str) or not snapshot.summary.strip():
            defects.append("summary is required")
        try:
            if not isinstance(snapshot.published_at, str):
                raise ValueError
            datetime.fromisoformat(snapshot.published_at.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            defects.append("published_at must be ISO-8601")
        try:
            if not isinstance(snapshot.archive_date, str):
                raise ValueError
            date.fromisoformat(snapshot.archive_date)
        except (TypeError, ValueError):
            defects.append("archive_date must be YYYY-MM-DD")
        if (
            not isinstance(snapshot.archive_filename, str)
            or not EpisodeSourceRepository.is_safe_archive_filename(snapshot.archive_filename)
        ):
            defects.append("archive_filename must be one safe path segment")
        transcript_bytes = (
            snapshot.transcript.encode("utf-8")
            if isinstance(snapshot.transcript, str)
            else b""
        )
        if not isinstance(snapshot.transcript, str) or len(transcript_bytes) < MIN_TRANSCRIPT_BYTES:
            defects.append("transcript must contain at least 1000 UTF-8 bytes")
        heading_pattern = rf"^#\s+EP0*{snapshot.number}\b"
        if not isinstance(snapshot.transcript, str) or not re.search(
            heading_pattern, snapshot.transcript, re.IGNORECASE | re.MULTILINE
        ):
            defects.append("transcript heading must match the episode number")
        stripped = snapshot.transcript.lstrip().lower() if isinstance(snapshot.transcript, str) else ""
        if stripped.startswith("<!doctype html") or stripped.startswith("<html"):
            defects.append("transcript must be Markdown, not HTML")
        required_urls = REQUIRED_SOURCE_URLS
        if not isinstance(snapshot.transcription, Mapping):
            defects.append("transcription provenance must be a mapping")
        elif snapshot.transcription:
            required_urls = frozenset({"youtube_metadata", "duration_metadata", "audio", "transcript"})
            details = snapshot.transcription
            if not isinstance(details, Mapping) or not all(
                isinstance(details.get(key), str) and details[key].strip()
                for key in ("engine", "model", "audio_url", "audio_sha256")
            ):
                defects.append("transcription provenance is incomplete")
            else:
                if not EpisodeSourceRepository._is_absolute_url(details["audio_url"]):
                    defects.append("transcription audio_url must be an absolute URL")
                if not re.fullmatch(r"[a-f0-9]{64}", details["audio_sha256"]):
                    defects.append("transcription audio_sha256 must be a SHA-256 digest")
                if isinstance(snapshot.source_urls, Mapping) and snapshot.source_urls.get("audio") != details["audio_url"]:
                    defects.append("transcription audio_url must match source_urls audio")
            if isinstance(details, Mapping) and not all(isinstance(k, str) and isinstance(v, str) for k, v in details.items()):
                defects.append("transcription provenance values must be strings")
        if not isinstance(snapshot.source_urls, Mapping) or not required_urls.issubset(snapshot.source_urls):
            defects.append("source_urls are incomplete")
        elif any(
            not EpisodeSourceRepository._is_absolute_url(snapshot.source_urls[key])
            for key in required_urls
        ):
            defects.append("source_urls must contain non-empty absolute URLs")
        try:
            if not isinstance(snapshot.fetched_at, str):
                raise ValueError
            datetime.fromisoformat(snapshot.fetched_at.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            defects.append("fetched_at must be ISO-8601")
        if defects:
            raise InvalidSnapshotError("; ".join(defects))

    @staticmethod
    def _manifest(snapshot: EpisodeSourceSnapshot, transcript_bytes: bytes) -> dict:
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "episode": snapshot.number,
            "official": {
                "youtube_id": snapshot.youtube_id,
                "youtube_title": snapshot.youtube_title,
                "published_at": snapshot.published_at,
                "duration_seconds": snapshot.duration_seconds,
            },
            "archive": {
                "filename": snapshot.archive_filename,
                "display_title": snapshot.display_title,
                "date": snapshot.archive_date,
                "summary": snapshot.summary,
            },
            "transcript": {
                "path": TRANSCRIPT_FILENAME,
                "size_bytes": len(transcript_bytes),
                "sha256": _sha256(transcript_bytes),
            },
            "provenance": {
                "source_urls": dict(sorted(snapshot.source_urls.items())),
                "fetched_at": snapshot.fetched_at,
            },
        }
        if snapshot.transcription:
            manifest["transcript"]["transcription"] = dict(snapshot.transcription)
        content = {
            "official": manifest["official"],
            "archive": manifest["archive"],
            "transcript": manifest["transcript"],
        }
        manifest["content_sha256"] = _sha256(
            json.dumps(
                content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        return manifest

    @staticmethod
    def _read_manifest(directory: Path) -> dict:
        return json.loads((directory / MANIFEST_FILENAME).read_text(encoding="utf-8"))

    def commit(self, snapshot: EpisodeSourceSnapshot, force: bool = False) -> str:
        """Validate and install a new snapshot directory."""
        self._validate_snapshot(snapshot)
        try:
            target = self._episode_dir(snapshot.number)
            transcript_bytes = snapshot.transcript.encode("utf-8")
            manifest = self._manifest(snapshot, transcript_bytes)
            if target.exists():
                existing_report = self._verify_directory(target, snapshot.number)
                if existing_report.is_valid:
                    existing_manifest = self._read_manifest(target)
                    if existing_manifest.get("content_sha256") == manifest["content_sha256"]:
                        # A corrected ASR source URL must replace local-only
                        # provenance even when transcript bytes are identical.
                        old_urls = existing_manifest.get("provenance", {}).get("source_urls")
                        new_urls = manifest["provenance"]["source_urls"]
                        if not (force and snapshot.transcription and old_urls != new_urls):
                            return "unchanged"
                if not force:
                    raise SnapshotConflictError(
                        f"EP{snapshot.number} already exists with different content; "
                        "changed content requires --force"
                    )

            self.snapshot_root.mkdir(parents=True, exist_ok=True)
            stage = Path(
                tempfile.mkdtemp(
                    prefix=f".{self._episode_dir_name(snapshot.number)}.",
                    suffix=".staging",
                    dir=self.snapshot_root,
                )
            )
        except (InvalidSnapshotError, SnapshotConflictError, SnapshotCommitError):
            raise
        except OSError as exc:
            raise SnapshotCommitError(str(exc)) from exc

        primary_error: BaseException | None = None
        try:
            try:
                (stage / TRANSCRIPT_FILENAME).write_bytes(transcript_bytes)
                (stage / MANIFEST_FILENAME).write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except OSError as exc:
                raise SnapshotCommitError(str(exc)) from exc

            report = self._verify_directory(stage, snapshot.number)
            if not report.is_valid:
                raise InvalidSnapshotError("; ".join(report.defects))
            if not target.exists():
                try:
                    os.replace(stage, target)
                except OSError as exc:
                    raise SnapshotCommitError(str(exc)) from exc
                return "created"

            backup = self.snapshot_root / (
                f".{self._episode_dir_name(snapshot.number)}.{uuid4().hex}.backup"
            )
            try:
                os.replace(target, backup)
                try:
                    os.replace(stage, target)
                except OSError as install_error:
                    try:
                        os.replace(backup, target)
                    except OSError as restore_error:
                        raise SnapshotCommitError(
                            f"{install_error}; rollback also failed: {restore_error}"
                        ) from install_error
                    raise SnapshotCommitError(str(install_error)) from install_error

                installed_report = self._verify_directory(target, snapshot.number)
                if not installed_report.is_valid:
                    try:
                        shutil.rmtree(target)
                    except OSError as remove_error:
                        raise SnapshotCommitError(
                            "installed snapshot failed verification and could not be "
                            f"removed: {remove_error}"
                        ) from remove_error
                    try:
                        os.replace(backup, target)
                    except OSError as restore_error:
                        raise SnapshotCommitError(
                            "installed snapshot failed verification; rollback also "
                            f"failed: {restore_error}"
                        ) from restore_error
                    raise SnapshotCommitError(
                        "installed snapshot failed verification: "
                        + "; ".join(installed_report.defects)
                    )
                try:
                    shutil.rmtree(backup)
                except OSError as exc:
                    raise SnapshotCommitError(str(exc)) from exc
            except SnapshotCommitError:
                raise
            except OSError as exc:
                if backup.exists() and not target.exists():
                    try:
                        os.replace(backup, target)
                    except OSError as restore_error:
                        raise SnapshotCommitError(
                            f"{exc}; rollback also failed: {restore_error}"
                        ) from exc
                raise SnapshotCommitError(str(exc)) from exc
            return "updated"
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            try:
                if stage.exists():
                    shutil.rmtree(stage)
            except OSError as cleanup_error:
                if primary_error is None:
                    raise SnapshotCommitError(str(cleanup_error)) from cleanup_error

    def _verify_directory(self, directory: Path, number: int) -> EpisodeSourceVerification:
        defects: list[str] = []
        manifest_path = directory / MANIFEST_FILENAME
        transcript_path = directory / TRANSCRIPT_FILENAME
        if not manifest_path.is_file():
            defects.append("snapshot.json is missing")
            return EpisodeSourceVerification(number=number, defects=tuple(defects))
        if not transcript_path.is_file():
            defects.append("transcript.md is missing")
            return EpisodeSourceVerification(number=number, defects=tuple(defects))
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            defects.append(f"snapshot.json is invalid: {exc}")
            return EpisodeSourceVerification(number=number, defects=tuple(defects))
        if not isinstance(manifest, dict):
            defects.append("snapshot.json must be a JSON object")
            return EpisodeSourceVerification(number=number, defects=tuple(defects))
        if manifest.get("schema_version") != SCHEMA_VERSION:
            defects.append("schema_version is unsupported")
        if manifest.get("episode") != number:
            defects.append("manifest episode does not match directory")
        try:
            transcript_bytes = transcript_path.read_bytes()
            transcript_text = transcript_bytes.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            defects.append(f"transcript.md is invalid: {exc}")
            return EpisodeSourceVerification(number=number, defects=tuple(defects))
        official = manifest.get("official")
        archive = manifest.get("archive")
        provenance = manifest.get("provenance")
        transcript_meta = manifest.get("transcript")
        if not isinstance(official, dict):
            defects.append("official schema is invalid")
            official = {}
        if not isinstance(archive, dict):
            defects.append("archive schema is invalid")
            archive = {}
        if not isinstance(provenance, dict):
            defects.append("provenance schema is invalid")
            provenance = {}
        if not isinstance(transcript_meta, dict):
            defects.append("transcript schema is invalid")
            transcript_meta = {}
        required_official = {"youtube_id", "youtube_title", "published_at", "duration_seconds"}
        required_archive = {"filename", "display_title", "date", "summary"}
        required_provenance = {"source_urls", "fetched_at"}
        if not required_official.issubset(official):
            defects.append("official schema is incomplete")
        if not required_archive.issubset(archive):
            defects.append("archive schema is incomplete")
        if not required_provenance.issubset(provenance):
            defects.append("provenance schema is incomplete")
        if not (
            isinstance(manifest.get("episode"), int)
            and not isinstance(manifest.get("episode"), bool)
            and isinstance(official.get("youtube_id"), str)
            and isinstance(official.get("youtube_title"), str)
            and isinstance(official.get("published_at"), str)
            and isinstance(official.get("duration_seconds"), int)
            and not isinstance(official.get("duration_seconds"), bool)
        ):
            defects.append("official schema has invalid field types")
        if not all(
            isinstance(archive.get(field), str)
            for field in ("filename", "display_title", "date", "summary")
        ):
            defects.append("archive schema has invalid field types")
        if not (
            isinstance(provenance.get("source_urls"), Mapping)
            and isinstance(provenance.get("fetched_at"), str)
        ):
            defects.append("provenance schema has invalid field types")
        if not (
            isinstance(transcript_meta.get("path"), str)
            and isinstance(transcript_meta.get("size_bytes"), int)
            and not isinstance(transcript_meta.get("size_bytes"), bool)
            and isinstance(transcript_meta.get("sha256"), str)
        ):
            defects.append("transcript schema has invalid field types")
        if transcript_meta.get("path") != TRANSCRIPT_FILENAME:
            defects.append("transcript path is invalid")
        if transcript_meta.get("size_bytes") != len(transcript_bytes):
            defects.append("transcript size_bytes does not match")
        if transcript_meta.get("sha256") != _sha256(transcript_bytes):
            defects.append("transcript sha256 does not match")
        hashed_content = {
            "official": manifest.get("official"),
            "archive": manifest.get("archive"),
            "transcript": transcript_meta,
        }
        actual_content_sha256 = _sha256(
            json.dumps(
                hashed_content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if manifest.get("content_sha256") != actual_content_sha256:
            defects.append("content_sha256 does not match manifest content")
        try:
            self._validate_snapshot(
                EpisodeSourceSnapshot(
                    number=manifest.get("episode"),
                    youtube_id=official.get("youtube_id", ""),
                    youtube_title=official.get("youtube_title", ""),
                    published_at=official.get("published_at", ""),
                    duration_seconds=official.get("duration_seconds", 0),
                    archive_filename=archive.get("filename", ""),
                    display_title=archive.get("display_title", ""),
                    archive_date=archive.get("date", ""),
                    summary=archive.get("summary", ""),
                    transcript=transcript_text,
                    source_urls=provenance.get("source_urls", {}),
                    fetched_at=provenance.get("fetched_at", ""),
                    transcription=transcript_meta.get("transcription", {}),
                )
            )
        except (InvalidSnapshotError, TypeError) as exc:
            defects.extend(str(exc).split("; "))
        return EpisodeSourceVerification(number=number, defects=tuple(defects))

    def verify(self, number: int) -> EpisodeSourceVerification:
        """Verify one normalized snapshot without changing it."""
        return self._verify_directory(self._episode_dir(number), number)

    @staticmethod
    def _parse_episode_number(title: str) -> int | None:
        match = re.search(r"\bEP\s*(\d+)\b", title, re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _load_legacy(self) -> None:
        if self._legacy_channel_entries is not None:
            return
        self._legacy_channel_entries = {}
        self._legacy_archive_entries = {}
        if self.legacy_channel_path.exists():
            channel_data = json.loads(self.legacy_channel_path.read_text(encoding="utf-8"))
            for entry in channel_data.get("entries", []):
                number = self._parse_episode_number(entry.get("title", ""))
                if number is not None:
                    self._legacy_channel_entries[number] = entry
        if self.legacy_archive_path.exists():
            archive_data = json.loads(self.legacy_archive_path.read_text(encoding="utf-8"))
            for entry in archive_data:
                number = entry.get("number")
                if isinstance(number, int):
                    self._legacy_archive_entries[number] = entry

    def _normalized_numbers(self) -> set[int]:
        if not self.snapshot_root.exists():
            return set()
        numbers: set[int] = set()
        for directory in self.snapshot_root.glob("EP[0-9][0-9][0-9][0-9]"):
            match = re.fullmatch(r"EP(\d{4})", directory.name)
            if not match:
                continue
            number = int(match.group(1))
            if self._verify_directory(directory, number).is_valid:
                numbers.add(number)
        return numbers

    @property
    def episode_numbers(self) -> list[int]:
        """Return the union of usable legacy and normalized episode sources."""
        self._load_legacy()
        assert self._legacy_channel_entries is not None
        assert self._legacy_archive_entries is not None
        legacy = {
            number
            for number in self._legacy_archive_entries
            if (
                number in self._legacy_channel_entries
                or (self.legacy_transcript_dir / f"EP{number:04d}.md").exists()
            )
        }
        return sorted(legacy | self._normalized_numbers())

    @property
    def legacy_channel_count(self) -> int:
        self._load_legacy()
        assert self._legacy_channel_entries is not None
        return len(self._legacy_channel_entries)

    @property
    def legacy_archive_count(self) -> int:
        self._load_legacy()
        assert self._legacy_archive_entries is not None
        return len(self._legacy_archive_entries)

    @property
    def legacy_transcript_count(self) -> int:
        return len(list(self.legacy_transcript_dir.glob("EP*.md")))

    @property
    def normalized_snapshot_count(self) -> int:
        return len(self._normalized_numbers())

    @property
    def invalid_snapshot_count(self) -> int:
        if not self.snapshot_root.exists():
            return 0
        invalid = 0
        for directory in self.snapshot_root.glob("EP[0-9][0-9][0-9][0-9]"):
            match = re.fullmatch(r"EP(\d{4})", directory.name)
            if match and not self._verify_directory(
                directory,
                int(match.group(1)),
            ).is_valid:
                invalid += 1
        return invalid

    def _normalized_manifest(self, number: int) -> dict | None:
        directory = self._episode_dir(number)
        if not directory.exists():
            return None
        report = self._verify_directory(directory, number)
        if not report.is_valid:
            raise InvalidSnapshotError(
                f"EP{number} normalized snapshot is invalid: " + "; ".join(report.defects)
            )
        return self._read_manifest(directory)

    def get_metadata(self, number: int) -> EpisodeMetadata:
        """Return normalized metadata when present, otherwise legacy metadata."""
        manifest = self._normalized_manifest(number)
        if manifest is not None:
            official = manifest["official"]
            archive = manifest["archive"]
            transcription = manifest["transcript"].get("transcription", {})
            archive_url = "" if transcription else (
                f"{self.archive_base_url}episode.html?file={quote(archive['filename'])}"
            )
            return EpisodeMetadata(
                number=number,
                youtube_id=official["youtube_id"],
                youtube_url=f"https://www.youtube.com/watch?v={official['youtube_id']}",
                youtube_title=official["youtube_title"],
                display_title=archive["display_title"],
                date=archive["date"],
                date_source="official_metadata" if transcription else "transcript_archive",
                duration_str=format_duration(official["duration_seconds"]),
                duration_seconds=official["duration_seconds"],
                archive_url=archive_url,
                summary=archive["summary"].strip(),
                transcription=transcription,
            )

        self._load_legacy()
        assert self._legacy_channel_entries is not None
        assert self._legacy_archive_entries is not None
        channel_entry = self._legacy_channel_entries.get(number)
        archive_entry = self._legacy_archive_entries.get(number)
        if not archive_entry or (
            not channel_entry
            and not (self.legacy_transcript_dir / f"EP{number:04d}.md").exists()
        ):
            raise ValueError(f"Metadata not found for EP{number}")

        if channel_entry:
            youtube_id = channel_entry["id"]
            duration_seconds = round(channel_entry.get("duration") or 0)
            original_title = channel_entry.get("title") or f"EP{number}"
            duration_str = format_duration(channel_entry.get("duration"))
            youtube_url = f"https://www.youtube.com/watch?v={youtube_id}"
        else:
            youtube_id = ""
            duration_seconds = 0
            original_title = f"EP{number} | {archive_entry.get('title', '')}"
            duration_str = "未知"
            youtube_url = "https://www.youtube.com/@Gooaye/videos"

        display_title = (
            archive_entry.get("display_title")
            or archive_entry.get("title")
            or original_title
        )
        archive_filename = archive_entry.get("filename", f"EP{number}.md")
        archive_date = archive_entry.get("date")
        if archive_date:
            date_value, date_source = archive_date, "transcript_archive"
        elif channel_entry:
            sample_path = (
                self.legacy_channel_path.parent
                / "samples"
                / f"{youtube_id}.metadata.json"
            )
            if sample_path.exists():
                try:
                    upload_date = json.loads(
                        sample_path.read_text(encoding="utf-8")
                    ).get("upload_date")
                    date_value = datetime.strptime(
                        str(upload_date), "%Y%m%d"
                    ).date().isoformat()
                    date_source = "youtube_metadata"
                except (OSError, TypeError, ValueError, json.JSONDecodeError):
                    date_value, date_source = "未知", "unknown"
            else:
                date_value, date_source = "未知", "unknown"
        else:
            date_value, date_source = "未知", "unknown"
        return EpisodeMetadata(
            number=number,
            youtube_id=youtube_id,
            youtube_url=youtube_url,
            youtube_title=original_title,
            display_title=display_title,
            date=date_value,
            date_source=date_source,
            duration_str=duration_str,
            duration_seconds=duration_seconds,
            archive_url=(
                f"{self.archive_base_url}episode.html?file={quote(archive_filename)}"
            ),
            summary=archive_entry.get("summary", "").strip(),
        )

    def load_transcript(self, number: int) -> str:
        """Load a normalized transcript when present, otherwise the legacy file."""
        manifest = self._normalized_manifest(number)
        if manifest is not None:
            return (self._episode_dir(number) / TRANSCRIPT_FILENAME).read_text(
                encoding="utf-8"
            )
        path = self.legacy_transcript_dir / f"EP{number:04d}.md"
        if not path.exists():
            raise FileNotFoundError(f"Missing transcript for EP{number}: {path}")
        return path.read_text(encoding="utf-8")

    def get_legacy_acquisition_metadata(self, number: int) -> dict | None:
        """Expose accepted legacy official metadata for reacquiring an old episode."""
        self._load_legacy()
        assert self._legacy_channel_entries is not None
        assert self._legacy_archive_entries is not None
        channel = self._legacy_channel_entries.get(number)
        archive = self._legacy_archive_entries.get(number)
        if not channel or not archive or not archive.get("date"):
            return None
        duration_seconds = round(channel.get("duration") or 0)
        if not channel.get("id") or duration_seconds <= 0:
            return None
        return {
            "number": number,
            "youtube_id": channel["id"],
            "youtube_title": channel.get("title") or f"EP{number}",
            "published_at": f"{archive['date']}T00:00:00+00:00",
            "duration_seconds": duration_seconds,
            "metadata_source": self.legacy_channel_path.resolve().as_uri(),
        }


__all__ = [
    "EpisodeSourceRepository",
    "EpisodeSourceSnapshot",
    "EpisodeSourceVerification",
    "EpisodeSourceError",
    "InvalidSnapshotError",
    "SnapshotCommitError",
    "SnapshotConflictError",
    "MIN_TRANSCRIPT_BYTES",
]
