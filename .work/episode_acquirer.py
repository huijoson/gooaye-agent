"""Acquire one complete episode source snapshot from public upstream feeds."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Callable, Protocol
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from domain import EpisodeSourceSnapshot, EpisodeSourceVerification
from episode_source_repository import MIN_TRANSCRIPT_BYTES, EpisodeSourceRepository


YOUTUBE_FEED_URL = (
    "https://www.youtube.com/feeds/videos.xml?"
    "channel_id=UC23rnlQU_qE3cec9x709peA"
)
SOUNDON_FEED_URL = (
    "https://feeds.soundon.fm/podcasts/954689a5-3096-43a4-a80b-7810b219cef3.xml"
)
ARCHIVE_INDEX_URL = "https://whatmkreallysaid.com/episodes.json"
ARCHIVE_EPISODES_URL = "https://whatmkreallysaid.com/episodes/"

ATOM = "http://www.w3.org/2005/Atom"
YOUTUBE = "http://www.youtube.com/xml/schemas/2015"
ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"


@dataclass(frozen=True)
class HttpResponse:
    url: str
    status: int
    content_type: str
    body: bytes


class HttpClient(Protocol):
    def get(self, url: str, accept: str) -> HttpResponse: ...


class UrlLibHttpClient:
    """Small HTTP adapter that preserves status, content type, and bytes."""

    def __init__(self, timeout_seconds: float = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def get(self, url: str, accept: str) -> HttpResponse:
        request = Request(
            url,
            headers={
                "Accept": accept,
                "User-Agent": "gooaye-agent-episode-acquirer/1",
            },
        )
        try:
            response = urlopen(request, timeout=self.timeout_seconds)
        except HTTPError as exc:
            return HttpResponse(
                url=exc.geturl(),
                status=exc.code,
                content_type=exc.headers.get("Content-Type", ""),
                body=exc.read(),
            )
        with response:
            return HttpResponse(
                url=response.geturl(),
                status=response.status,
                content_type=response.headers.get("Content-Type", ""),
                body=response.read(),
            )


@dataclass(frozen=True)
class AcquisitionResult:
    number: int
    status: str
    youtube_id: str
    duration_seconds: int
    snapshot_path: str
    verification: EpisodeSourceVerification


class EpisodeAcquisitionError(RuntimeError):
    """Base error for upstream episode acquisition."""


class SourceFormatError(EpisodeAcquisitionError):
    """Raised when an upstream response does not match its public format."""


class SourceMismatchError(EpisodeAcquisitionError):
    """Raised when upstream authorities disagree on episode identity."""


class EpisodeNotInOfficialFeedError(EpisodeAcquisitionError):
    """Raised when an unknown episode is outside the incremental feed window."""


class ArchivePendingError(EpisodeAcquisitionError):
    """Raised when an official episode has no complete archive transcript yet."""


class SourceNetworkError(EpisodeAcquisitionError):
    """Raised when an upstream source cannot be reached."""


def parse_episode_number(title: str) -> int | None:
    match = re.search(r"\bEP\s*(\d+)\b", title, re.IGNORECASE)
    return int(match.group(1)) if match else None


def parse_duration(value: str) -> int:
    parts = value.strip().split(":")
    if not parts or any(not part.isdigit() for part in parts) or len(parts) > 3:
        raise SourceFormatError(f"Invalid duration: {value!r}")
    numbers = [int(part) for part in parts]
    if len(numbers) == 1:
        return numbers[0]
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]


class EpisodeAcquirer:
    """Translate upstream formats and commit one verified source snapshot."""

    def __init__(
        self,
        repository: EpisodeSourceRepository,
        http_client: HttpClient,
        clock: Callable[[], datetime] | None = None,
        youtube_feed_url: str = YOUTUBE_FEED_URL,
        soundon_feed_url: str = SOUNDON_FEED_URL,
        archive_index_url: str = ARCHIVE_INDEX_URL,
        archive_episodes_url: str = ARCHIVE_EPISODES_URL,
    ) -> None:
        self.repository = repository
        self.http_client = http_client
        self.clock = clock or (lambda: datetime.now(UTC))
        self.youtube_feed_url = youtube_feed_url
        self.soundon_feed_url = soundon_feed_url
        self.archive_index_url = archive_index_url
        self.archive_episodes_url = archive_episodes_url.rstrip("/") + "/"

    def _response_body(
        self,
        url: str,
        accept: str,
        expected_content_types: tuple[str, ...],
    ) -> bytes:
        try:
            response = self.http_client.get(url, accept)
        except (OSError, TimeoutError) as exc:
            raise SourceNetworkError(f"{url}: {exc}") from exc
        if response.status != 200:
            raise SourceFormatError(f"{url} returned HTTP {response.status}")
        media_type = response.content_type.partition(";")[0].strip().lower()
        if media_type not in expected_content_types:
            raise SourceFormatError(
                f"{url} returned unexpected content type {response.content_type!r}"
            )
        return response.body

    def _youtube_entries(self) -> list[dict]:
        body = self._response_body(
            self.youtube_feed_url,
            "application/atom+xml, application/xml",
            ("application/atom+xml", "application/xml", "text/xml"),
        )
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise SourceFormatError(f"YouTube feed is invalid XML: {exc}") from exc
        entries: list[dict] = []
        for entry in root.findall(f"{{{ATOM}}}entry"):
            title = (entry.findtext(f"{{{ATOM}}}title") or "").strip()
            number = parse_episode_number(title)
            if number is None:
                continue
            youtube_id = (entry.findtext(f"{{{YOUTUBE}}}videoId") or "").strip()
            published_at = (entry.findtext(f"{{{ATOM}}}published") or "").strip()
            if not youtube_id or not published_at:
                raise SourceFormatError(f"YouTube entry for EP{number} is incomplete")
            entries.append(
                {
                    "number": number,
                    "youtube_id": youtube_id,
                    "youtube_title": title,
                    "published_at": published_at,
                }
            )
        if not entries:
            raise SourceFormatError("YouTube feed contains no episode entries")
        return entries

    def _youtube_entry(self, number: int) -> dict:
        for entry in self._youtube_entries():
            if entry["number"] == number:
                return entry
        raise EpisodeNotInOfficialFeedError(
            f"EP{number} is not present in the official feed window"
        )

    def _soundon_entry(self, number: int) -> dict:
        body = self._response_body(
            self.soundon_feed_url,
            "application/rss+xml, application/xml",
            ("application/rss+xml", "application/xml", "text/xml"),
        )
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise SourceFormatError(f"SoundOn feed is invalid XML: {exc}") from exc
        for item in root.findall("./channel/item"):
            episode_text = (item.findtext(f"{{{ITUNES}}}episode") or "").strip()
            title = (item.findtext("title") or "").strip()
            title_number = parse_episode_number(title)
            if episode_text and not episode_text.isdigit():
                raise SourceFormatError("SoundOn itunes:episode is invalid")
            item_number = int(episode_text) if episode_text else title_number
            if (
                episode_text
                and title_number is not None
                and item_number != title_number
            ):
                raise SourceMismatchError(
                    "SoundOn itunes:episode disagrees with the title episode number"
                )
            if item_number != number:
                continue
            published_text = (item.findtext("pubDate") or "").strip()
            duration_text = (item.findtext(f"{{{ITUNES}}}duration") or "").strip()
            if not published_text or not duration_text:
                raise SourceFormatError(f"SoundOn entry for EP{number} is incomplete")
            try:
                published_at = parsedate_to_datetime(published_text)
            except (TypeError, ValueError) as exc:
                raise SourceFormatError(
                    f"SoundOn pubDate for EP{number} is invalid"
                ) from exc
            return {
                "number": number,
                "published_at": published_at,
                "duration_seconds": parse_duration(duration_text),
            }
        raise SourceMismatchError(f"EP{number} is missing from the SoundOn feed")

    def _archive_entry(self, number: int) -> dict:
        body = self._response_body(
            self.archive_index_url,
            "application/json",
            ("application/json", "text/json"),
        )
        try:
            entries = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceFormatError(f"Archive index is invalid JSON: {exc}") from exc
        if not isinstance(entries, list):
            raise SourceFormatError("Archive index must be a JSON array")
        for entry in entries:
            if isinstance(entry, dict) and entry.get("number") == number:
                return entry
        raise ArchivePendingError(f"EP{number} is not present in the archive index")

    @staticmethod
    def _archive_metadata(entry: dict, number: int) -> tuple[str, str, str, str]:
        """Validate and select the archive fields before fetching its transcript."""
        filename = entry.get("filename")
        if not isinstance(filename, str):
            raise SourceFormatError(f"EP{number} archive filename must be a string")
        if not EpisodeSourceRepository.is_safe_archive_filename(filename):
            raise SourceFormatError(f"EP{number} archive filename is unsafe")

        if "display_title" in entry and not isinstance(entry["display_title"], str):
            raise SourceFormatError(f"EP{number} display_title must be a string")
        display_title = entry.get("display_title")
        if not isinstance(display_title, str) or not display_title.strip():
            display_title = entry.get("title")
        if not isinstance(display_title, str) or not display_title.strip():
            raise SourceFormatError(
                f"EP{number} display_title or title must be a non-empty string"
            )

        archive_date = entry.get("date")
        if not isinstance(archive_date, str) or not archive_date.strip():
            raise SourceFormatError(f"EP{number} date must be a non-empty string")
        summary = entry.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise SourceFormatError(f"EP{number} summary must be a non-empty string")
        return filename, display_title, archive_date, summary

    @staticmethod
    def _cross_check_dates(
        number: int,
        youtube_published_at: str,
        soundon_published_at: datetime,
        archive_date: str,
    ) -> None:
        try:
            youtube_date = datetime.fromisoformat(
                youtube_published_at.replace("Z", "+00:00")
            ).date()
            archive_day = datetime.strptime(archive_date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise SourceFormatError(f"EP{number} has an invalid publication date") from exc
        if len({youtube_date, soundon_published_at.date(), archive_day}) != 1:
            raise SourceMismatchError(
                f"EP{number} publication dates disagree across upstream sources"
            )

    def acquire(self, number: int, force: bool = False) -> AcquisitionResult:
        """Acquire and persist one complete source snapshot."""
        return self._acquire(number, force=force)

    def _acquire(
        self,
        number: int,
        force: bool,
        youtube_entry: dict | None = None,
    ) -> AcquisitionResult:
        youtube = youtube_entry
        if youtube is None:
            try:
                youtube = self._youtube_entry(number)
            except EpisodeNotInOfficialFeedError:
                legacy = self.repository.get_legacy_acquisition_metadata(number)
                if legacy is None:
                    raise
                youtube = legacy
                soundon = {
                    "number": number,
                    "published_at": datetime.fromisoformat(legacy["published_at"]),
                    "duration_seconds": legacy["duration_seconds"],
                }
                youtube_metadata_source = legacy["metadata_source"]
                duration_metadata_source = legacy["metadata_source"]
            else:
                soundon = self._soundon_entry(number)
                youtube_metadata_source = self.youtube_feed_url
                duration_metadata_source = self.soundon_feed_url
        else:
            soundon = self._soundon_entry(number)
            youtube_metadata_source = self.youtube_feed_url
            duration_metadata_source = self.soundon_feed_url
        archive = self._archive_entry(number)
        archive_filename, display_title, archive_date, summary = self._archive_metadata(
            archive, number
        )
        transcript_url = self.archive_episodes_url + quote(archive_filename, safe="")
        try:
            transcript_body = self._response_body(
                transcript_url,
                "text/markdown, text/plain",
                ("text/markdown", "text/plain"),
            )
        except SourceFormatError as exc:
            if "HTTP 404" in str(exc):
                raise ArchivePendingError(
                    f"EP{number} transcript is not ready in the archive"
                ) from exc
            raise
        try:
            transcript_text = transcript_body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceFormatError(f"EP{number} transcript is not UTF-8") from exc
        if len(transcript_body) < MIN_TRANSCRIPT_BYTES:
            raise SourceFormatError(
                f"EP{number} transcript must contain at least 1000 UTF-8 bytes"
            )
        if not re.search(
            rf"^#\s+EP0*{number}\b",
            transcript_text,
            re.IGNORECASE | re.MULTILINE,
        ):
            raise SourceMismatchError(
                f"EP{number} transcript heading does not match the requested episode"
            )

        self._cross_check_dates(
            number,
            youtube["published_at"],
            soundon["published_at"],
            archive_date,
        )
        snapshot = EpisodeSourceSnapshot(
            number=number,
            youtube_id=youtube["youtube_id"],
            youtube_title=youtube["youtube_title"],
            published_at=youtube["published_at"],
            duration_seconds=soundon["duration_seconds"],
            archive_filename=archive_filename,
            display_title=display_title,
            archive_date=archive_date,
            summary=summary,
            transcript=transcript_text,
            source_urls={
                "youtube_metadata": youtube_metadata_source,
                "duration_metadata": duration_metadata_source,
                "archive_index": self.archive_index_url,
                "transcript": transcript_url,
            },
            fetched_at=self.clock().astimezone(UTC).isoformat(),
        )
        status = self.repository.commit(snapshot, force=force)
        verification = self.repository.verify(number)
        if not verification.is_valid:
            raise EpisodeAcquisitionError(
                f"EP{number} failed post-commit verification: "
                + "; ".join(verification.defects)
            )
        return AcquisitionResult(
            number=number,
            status=status,
            youtube_id=snapshot.youtube_id,
            duration_seconds=snapshot.duration_seconds,
            snapshot_path=str(self.repository.snapshot_root / f"EP{number:04d}"),
            verification=verification,
        )

    def acquire_latest(self, force: bool = False) -> AcquisitionResult:
        """Acquire the newest official episode without falling back when pending."""
        latest = max(self._youtube_entries(), key=lambda entry: entry["number"])
        return self._acquire(
            latest["number"],
            force=force,
            youtube_entry=latest,
        )


__all__ = [
    "ARCHIVE_INDEX_URL",
    "AcquisitionResult",
    "ArchivePendingError",
    "EpisodeAcquirer",
    "EpisodeAcquisitionError",
    "EpisodeNotInOfficialFeedError",
    "HttpResponse",
    "SOUNDON_FEED_URL",
    "SourceFormatError",
    "SourceMismatchError",
    "SourceNetworkError",
    "UrlLibHttpClient",
    "YOUTUBE_FEED_URL",
]
