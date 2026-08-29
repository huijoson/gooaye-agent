from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import quote

import pytest

from episode_acquirer import (
    ArchivePendingError,
    EpisodeAcquirer,
    EpisodeNotInOfficialFeedError,
    HttpResponse,
    SourceFormatError,
    SourceMismatchError,
    SourceNetworkError,
    UrlLibHttpClient,
)
from episode_source_repository import EpisodeSourceRepository


YOUTUBE_FEED_URL = (
    "https://www.youtube.com/feeds/videos.xml?"
    "channel_id=UC23rnlQU_qE3cec9x709peA"
)
SOUNDON_FEED_URL = (
    "https://feeds.soundon.fm/podcasts/954689a5-3096-43a4-a80b-7810b219cef3.xml"
)
ARCHIVE_INDEX_URL = "https://whatmkreallysaid.com/episodes.json"
ARCHIVE_FILENAME = "EP691_北海道敲門驚魂與人人一個Jarvis.md"
TRANSCRIPT_URL = "https://whatmkreallysaid.com/episodes/" + quote(ARCHIVE_FILENAME)


class FixtureHttpClient:
    def __init__(self, responses: dict[str, HttpResponse]) -> None:
        self.responses = responses
        self.requested_urls: list[str] = []

    def get(self, url: str, accept: str) -> HttpResponse:
        self.requested_urls.append(url)
        try:
            return self.responses[url]
        except KeyError as exc:
            raise AssertionError(f"Unexpected fixture URL: {url}") from exc


def make_repository(root: Path) -> EpisodeSourceRepository:
    return EpisodeSourceRepository(
        snapshot_root=root / "episode-sources",
        legacy_channel_path=root / "channel.json",
        legacy_archive_path=root / "episodes.json",
        legacy_transcript_dir=root / "full-transcripts",
    )


def youtube_feed(latest_number: int = 691) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Gooaye 股癌</title>
  <entry>
    <id>yt:video:J-e9oxqLzpc</id>
    <yt:videoId>J-e9oxqLzpc</yt:videoId>
    <title>EP{latest_number} | 🎂</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=J-e9oxqLzpc"/>
    <published>2026-08-26T08:23:12+00:00</published>
    <updated>2026-08-26T09:02:05+00:00</updated>
    <media:group>
      <media:title>EP{latest_number} | 🎂</media:title>
      <media:description>門外有人</media:description>
    </media:group>
  </entry>
</feed>
""".encode()


def soundon_feed(number: int = 691) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" version="2.0">
  <channel>
    <title>Gooaye 股癌</title>
    <item>
      <title>EP{number} | 🎂</title>
      <pubDate>Wed, 26 Aug 2026 07:30:00 GMT</pubDate>
      <guid>c12de84bd7424b7f8890706a192fd7d7a56226a3</guid>
      <itunes:episode>{number}</itunes:episode>
      <itunes:duration>00:49:55</itunes:duration>
      <description>門外有人</description>
    </item>
  </channel>
</rss>
""".encode()


def archive_index(include_691: bool = True) -> bytes:
    entries = []
    if include_691:
        entries.append(
            {
                "number": 691,
                "title": "北海道敲門驚魂與人人一個Jarvis",
                "filename": ARCHIVE_FILENAME,
                "description": "歡迎收聽股癌，我是謝孟恭。",
                "display_title": "北海道敲門驚魂與人人一個Jarvis",
                "summary": "北海道旅行、AI 工具與投資判斷之間的分工。",
                "date": "2026-08-26",
                "year": 2026,
                "month": 8,
                "day": 26,
                "month_name": "August",
                "date_display": "Aug 26, 2026",
                "date_short": "Aug 2026",
            }
        )
    return json.dumps(entries, ensure_ascii=False).encode()


def transcript(number: int = 691) -> bytes:
    return (
        f"# EP{number} 北海道敲門驚魂與人人一個Jarvis\n\n"
        + "這是完整逐字稿內容，涵蓋北海道旅行、AI 工具與投資判斷。" * 100
    ).encode()


def ep691_responses() -> dict[str, HttpResponse]:
    return {
        YOUTUBE_FEED_URL: HttpResponse(
            url=YOUTUBE_FEED_URL,
            status=200,
            content_type="application/atom+xml; charset=UTF-8",
            body=youtube_feed(),
        ),
        SOUNDON_FEED_URL: HttpResponse(
            url=SOUNDON_FEED_URL,
            status=200,
            content_type="application/rss+xml; charset=UTF-8",
            body=soundon_feed(),
        ),
        ARCHIVE_INDEX_URL: HttpResponse(
            url=ARCHIVE_INDEX_URL,
            status=200,
            content_type="application/json; charset=utf-8",
            body=archive_index(),
        ),
        TRANSCRIPT_URL: HttpResponse(
            url=TRANSCRIPT_URL,
            status=200,
            content_type="text/markdown; charset=utf-8",
            body=transcript(),
        ),
    }


def test_acquire_builds_ep691_from_all_authorities(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    acquirer = EpisodeAcquirer(
        repository=repository,
        http_client=FixtureHttpClient(ep691_responses()),
        clock=lambda: datetime(2026, 8, 28, 0, 0, tzinfo=UTC),
    )

    result = acquirer.acquire(691)

    assert result.number == 691
    assert result.status == "created"
    assert result.youtube_id == "J-e9oxqLzpc"
    assert result.duration_seconds == 2995
    assert result.verification.is_valid
    assert repository.get_metadata(691).display_title == "北海道敲門驚魂與人人一個Jarvis"
    assert repository.load_transcript(691).startswith("# EP691")


def test_latest_reports_archive_pending_instead_of_falling_back(tmp_path: Path) -> None:
    responses = ep691_responses()
    responses[YOUTUBE_FEED_URL] = HttpResponse(
        url=YOUTUBE_FEED_URL,
        status=200,
        content_type="application/atom+xml",
        body=youtube_feed(latest_number=692),
    )
    responses[SOUNDON_FEED_URL] = HttpResponse(
        url=SOUNDON_FEED_URL,
        status=200,
        content_type="application/rss+xml",
        body=soundon_feed(number=692),
    )

    acquirer = EpisodeAcquirer(
        repository=make_repository(tmp_path),
        http_client=FixtureHttpClient(responses),
    )

    with pytest.raises(ArchivePendingError, match="EP692"):
        acquirer.acquire_latest()


def test_latest_fetches_the_youtube_feed_only_once(tmp_path: Path) -> None:
    class OneShotYoutubeClient(FixtureHttpClient):
        youtube_calls = 0

        def get(self, url: str, accept: str) -> HttpResponse:
            if url == YOUTUBE_FEED_URL:
                self.youtube_calls += 1
                if self.youtube_calls > 1:
                    raise AssertionError("YouTube feed was fetched more than once")
            return super().get(url, accept)

    client = OneShotYoutubeClient(ep691_responses())
    acquirer = EpisodeAcquirer(
        repository=make_repository(tmp_path),
        http_client=client,
    )

    result = acquirer.acquire_latest()

    assert result.number == 691
    assert client.youtube_calls == 1


def test_unknown_episode_outside_the_official_feed_fails_explicitly(
    tmp_path: Path,
) -> None:
    acquirer = EpisodeAcquirer(
        repository=make_repository(tmp_path),
        http_client=FixtureHttpClient(ep691_responses()),
    )

    with pytest.raises(EpisodeNotInOfficialFeedError, match="EP700"):
        acquirer.acquire(700)


def test_acquire_rejects_publication_date_mismatch(tmp_path: Path) -> None:
    responses = ep691_responses()
    responses[SOUNDON_FEED_URL] = HttpResponse(
        url=SOUNDON_FEED_URL,
        status=200,
        content_type="application/rss+xml",
        body=soundon_feed().replace(b"26 Aug 2026", b"27 Aug 2026"),
    )
    acquirer = EpisodeAcquirer(
        repository=make_repository(tmp_path),
        http_client=FixtureHttpClient(responses),
    )

    with pytest.raises(SourceMismatchError, match="dates disagree"):
        acquirer.acquire(691)


def test_acquire_rejects_html_returned_as_a_transcript(tmp_path: Path) -> None:
    responses = ep691_responses()
    responses[TRANSCRIPT_URL] = HttpResponse(
        url=TRANSCRIPT_URL,
        status=200,
        content_type="text/html; charset=utf-8",
        body=b"<!doctype html><title>upstream error</title>",
    )
    acquirer = EpisodeAcquirer(
        repository=make_repository(tmp_path),
        http_client=FixtureHttpClient(responses),
    )

    with pytest.raises(SourceFormatError, match="content type"):
        acquirer.acquire(691)


def test_missing_archive_transcript_reports_archive_pending(tmp_path: Path) -> None:
    responses = ep691_responses()
    responses[TRANSCRIPT_URL] = HttpResponse(
        url=TRANSCRIPT_URL,
        status=404,
        content_type="text/plain; charset=utf-8",
        body=b"not found",
    )
    acquirer = EpisodeAcquirer(
        repository=make_repository(tmp_path),
        http_client=FixtureHttpClient(responses),
    )

    with pytest.raises(ArchivePendingError, match="EP691"):
        acquirer.acquire(691)


def test_network_timeout_is_reported_as_a_source_network_error(tmp_path: Path) -> None:
    class TimeoutHttpClient:
        def get(self, url: str, accept: str) -> HttpResponse:
            raise TimeoutError("timed out")

    acquirer = EpisodeAcquirer(
        repository=make_repository(tmp_path),
        http_client=TimeoutHttpClient(),
    )

    with pytest.raises(SourceNetworkError, match="timed out"):
        acquirer.acquire(691)


def test_transcript_heading_must_match_requested_episode(tmp_path: Path) -> None:
    responses = ep691_responses()
    responses[TRANSCRIPT_URL] = HttpResponse(
        url=TRANSCRIPT_URL,
        status=200,
        content_type="text/markdown; charset=utf-8",
        body=transcript(number=690),
    )
    acquirer = EpisodeAcquirer(
        repository=make_repository(tmp_path),
        http_client=FixtureHttpClient(responses),
    )

    with pytest.raises(SourceMismatchError, match="transcript"):
        acquirer.acquire(691)


@pytest.mark.parametrize("body", [b"<feed>", b"<feed></feed>"])
def test_malformed_or_empty_youtube_feed_is_a_typed_format_error(
    tmp_path: Path,
    body: bytes,
) -> None:
    responses = ep691_responses()
    responses[YOUTUBE_FEED_URL] = HttpResponse(
        url=YOUTUBE_FEED_URL,
        status=200,
        content_type="application/atom+xml",
        body=body,
    )

    with pytest.raises(SourceFormatError, match="YouTube"):
        EpisodeAcquirer(make_repository(tmp_path), FixtureHttpClient(responses)).acquire(691)


def test_malformed_soundon_xml_is_a_typed_format_error(tmp_path: Path) -> None:
    responses = ep691_responses()
    responses[SOUNDON_FEED_URL] = HttpResponse(
        url=SOUNDON_FEED_URL,
        status=200,
        content_type="application/rss+xml",
        body=b"<rss>",
    )

    with pytest.raises(SourceFormatError, match="SoundOn"):
        EpisodeAcquirer(make_repository(tmp_path), FixtureHttpClient(responses)).acquire(691)


def test_soundon_episode_id_that_conflicts_with_its_title_is_a_mismatch(
    tmp_path: Path,
) -> None:
    responses = ep691_responses()
    responses[SOUNDON_FEED_URL] = HttpResponse(
        url=SOUNDON_FEED_URL,
        status=200,
        content_type="application/rss+xml",
        body=soundon_feed().replace(b"<title>EP691", b"<title>EP690"),
    )

    with pytest.raises(SourceMismatchError, match="SoundOn.*disagrees"):
        EpisodeAcquirer(make_repository(tmp_path), FixtureHttpClient(responses)).acquire(691)


def test_missing_soundon_episode_is_a_source_mismatch(tmp_path: Path) -> None:
    responses = ep691_responses()
    responses[SOUNDON_FEED_URL] = HttpResponse(
        url=SOUNDON_FEED_URL,
        status=200,
        content_type="application/rss+xml",
        body=soundon_feed(number=690),
    )

    with pytest.raises(SourceMismatchError, match="missing from the SoundOn"):
        EpisodeAcquirer(make_repository(tmp_path), FixtureHttpClient(responses)).acquire(691)


def test_malformed_archive_json_is_a_typed_format_error(tmp_path: Path) -> None:
    responses = ep691_responses()
    responses[ARCHIVE_INDEX_URL] = HttpResponse(
        url=ARCHIVE_INDEX_URL,
        status=200,
        content_type="application/json",
        body=b"{not-json}",
    )

    with pytest.raises(SourceFormatError, match="Archive index"):
        EpisodeAcquirer(make_repository(tmp_path), FixtureHttpClient(responses)).acquire(691)


@pytest.mark.parametrize("filename", ["..", "."])
def test_unsafe_archive_filename_is_rejected_before_transcript_fetch_or_commit(
    tmp_path: Path,
    filename: str,
) -> None:
    responses = ep691_responses()
    entries = json.loads(archive_index().decode("utf-8"))
    entries[0]["filename"] = filename
    responses[ARCHIVE_INDEX_URL] = HttpResponse(
        url=ARCHIVE_INDEX_URL,
        status=200,
        content_type="application/json",
        body=json.dumps(entries, ensure_ascii=False).encode("utf-8"),
    )
    client = FixtureHttpClient(responses)
    repository = make_repository(tmp_path)

    with pytest.raises(SourceFormatError, match="archive filename"):
        EpisodeAcquirer(repository, client).acquire(691)

    assert all("/episodes/.." not in url and not url.endswith("/episodes/.") for url in client.requested_urls)
    assert not (tmp_path / "episode-sources/EP0691").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("filename", 691),
        ("display_title", ["malformed"]),
        ("date", [2026, 8, 26]),
        ("summary", ["malformed"]),
    ],
)
def test_malformed_archive_metadata_is_rejected_before_transcript_request_or_commit(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    responses = ep691_responses()
    entries = json.loads(archive_index().decode("utf-8"))
    entries[0][field] = value
    responses[ARCHIVE_INDEX_URL] = HttpResponse(
        url=ARCHIVE_INDEX_URL,
        status=200,
        content_type="application/json",
        body=json.dumps(entries, ensure_ascii=False).encode("utf-8"),
    )
    client = FixtureHttpClient(responses)
    repository = make_repository(tmp_path)

    with pytest.raises(SourceFormatError, match=field):
        EpisodeAcquirer(repository, client).acquire(691)

    assert TRANSCRIPT_URL not in client.requested_urls
    assert not (tmp_path / "episode-sources/EP0691").exists()


def test_incomplete_transcript_is_a_typed_format_error_before_commit(tmp_path: Path) -> None:
    responses = ep691_responses()
    responses[TRANSCRIPT_URL] = HttpResponse(
        url=TRANSCRIPT_URL,
        status=200,
        content_type="text/markdown",
        body=b"# EP691 valid heading\n\nshort body",
    )
    repository = make_repository(tmp_path)

    with pytest.raises(SourceFormatError, match="at least 1000 UTF-8 bytes"):
        EpisodeAcquirer(repository, FixtureHttpClient(responses)).acquire(691)

    assert not (tmp_path / "episode-sources/EP0691").exists()


def test_url_lib_http_client_preserves_success_and_http_error_responses() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/ok":
                body = "# EP691\n測試內容".encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
            else:
                body = b"not found"
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = UrlLibHttpClient(timeout_seconds=2)
        base_url = f"http://127.0.0.1:{server.server_port}"

        success = client.get(base_url + "/ok", "text/markdown")
        missing = client.get(base_url + "/missing", "text/plain")

        assert success.status == 200
        assert success.content_type == "text/markdown; charset=utf-8"
        assert success.body.startswith(b"# EP691")
        assert missing.status == 404
        assert missing.body == b"not found"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_existing_legacy_episode_can_be_reacquired_outside_the_feed_window(
    tmp_path: Path,
) -> None:
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
    legacy_archive_entry = {
        "number": 1,
        "filename": "EP1_歐洲疫情與股市崩跌.md",
        "display_title": "歐洲疫情與股市崩跌",
        "date": "2020-02-27",
        "summary": "歐洲疫情擴散與全球市場恐慌。",
    }
    archive_path.write_text(
        json.dumps([legacy_archive_entry], ensure_ascii=False),
        encoding="utf-8",
    )
    (transcript_dir / "EP0001.md").write_text("# EP1\n舊內容", encoding="utf-8")
    repository = EpisodeSourceRepository(
        snapshot_root=tmp_path / "episode-sources",
        legacy_channel_path=channel_path,
        legacy_archive_path=archive_path,
        legacy_transcript_dir=transcript_dir,
    )
    transcript_url = (
        "https://whatmkreallysaid.com/episodes/"
        + quote(legacy_archive_entry["filename"])
    )
    responses = ep691_responses()
    responses[ARCHIVE_INDEX_URL] = HttpResponse(
        url=ARCHIVE_INDEX_URL,
        status=200,
        content_type="application/json",
        body=json.dumps([legacy_archive_entry], ensure_ascii=False).encode(),
    )
    responses[transcript_url] = HttpResponse(
        url=transcript_url,
        status=200,
        content_type="text/markdown",
        body=("# EP1 歐洲疫情與股市崩跌\n\n" + "重新取得的完整逐字稿。" * 200).encode(),
    )
    acquirer = EpisodeAcquirer(
        repository=repository,
        http_client=FixtureHttpClient(responses),
        clock=lambda: datetime(2026, 8, 28, 0, 0, tzinfo=UTC),
    )

    result = acquirer.acquire(1, force=True)

    assert result.status == "created"
    assert result.youtube_id == "xLS-2whm8Aw"
    assert result.duration_seconds == 1423
    assert "重新取得" in repository.load_transcript(1)
    assert repository.verify(1).is_valid


@pytest.mark.skipif(
    os.environ.get("GOOAYE_LIVE_CONTRACT") != "1",
    reason="set GOOAYE_LIVE_CONTRACT=1 to call public upstream sources",
)
def test_live_ep691_sources_still_satisfy_the_acquisition_contract(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)
    acquirer = EpisodeAcquirer(
        repository=repository,
        http_client=UrlLibHttpClient(timeout_seconds=30),
    )

    result = acquirer.acquire(691)

    assert result.youtube_id == "J-e9oxqLzpc"
    assert result.duration_seconds == 2995
    assert result.verification.is_valid
    assert repository.get_metadata(691).date == "2026-08-26"
    assert len(repository.load_transcript(691).encode("utf-8")) >= 50_000
