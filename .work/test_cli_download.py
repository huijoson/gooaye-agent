from __future__ import annotations

import json
import os
import subprocess
import sys
from argparse import Namespace
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import cli


REPO_ROOT = Path(__file__).resolve().parent.parent


def run_cli(
    args: list[str],
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, ".work/cli.py", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=full_env,
    )


def test_download_requires_one_episode_selector() -> None:
    result = run_cli(["download"])

    assert result.returncode != 0
    assert "--episode" in result.stderr
    assert "--latest" in result.stderr


def test_download_rejects_both_episode_selectors() -> None:
    result = run_cli(["download", "--episode", "691", "--latest"])

    assert result.returncode != 0
    assert "not allowed with argument" in result.stderr


def test_download_help_documents_force_without_synthesis_flags() -> None:
    result = run_cli(["download", "--help"])

    assert result.returncode == 0
    assert "--episode" in result.stdout
    assert "--latest" in result.stdout
    assert "--force" in result.stdout
    assert "--resolver" not in result.stdout
    assert "--workers" not in result.stdout


def test_download_creates_verified_snapshot_and_second_run_is_unchanged(
    tmp_path: Path,
) -> None:
    youtube = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:yt="http://www.youtube.com/xml/schemas/2015">
  <entry>
    <yt:videoId>J-e9oxqLzpc</yt:videoId>
    <title>EP691 | birthday</title>
    <published>2026-08-26T08:23:12+00:00</published>
  </entry>
</feed>"""
    soundon = b"""<?xml version="1.0"?>
<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" version="2.0">
  <channel><item>
    <title>EP691 | birthday</title>
    <pubDate>Wed, 26 Aug 2026 07:30:00 GMT</pubDate>
    <itunes:episode>691</itunes:episode>
    <itunes:duration>00:49:55</itunes:duration>
  </item></channel>
</rss>"""
    archive = json.dumps(
        [
            {
                "number": 691,
                "title": "北海道敲門驚魂與人人一個Jarvis",
                "filename": "EP691_test.md",
                "description": "完整資料",
                "display_title": "北海道敲門驚魂與人人一個Jarvis",
                "summary": "北海道旅行、AI 工具與投資判斷之間的分工。",
                "date": "2026-08-26",
            }
        ],
        ensure_ascii=False,
    ).encode()
    transcript = (
        "# EP691 北海道敲門驚魂與人人一個Jarvis\n\n"
        + "這是完整逐字稿內容。" * 200
    ).encode()
    routes = {
        "/youtube.xml": (200, "application/atom+xml", youtube),
        "/soundon.xml": (200, "application/rss+xml", soundon),
        "/episodes.json": (200, "application/json", archive),
        "/episodes/EP691_test.md": (200, "text/markdown", transcript),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            status, content_type, body = routes.get(
                self.path,
                (404, "text/plain", b"not found"),
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    work_dir = tmp_path / ".work"
    env = {
        "GOOAYE_WORK_DIR": str(work_dir),
        "GOOAYE_YOUTUBE_FEED_URL": base_url + "/youtube.xml",
        "GOOAYE_SOUNDON_FEED_URL": base_url + "/soundon.xml",
        "GOOAYE_ARCHIVE_INDEX_URL": base_url + "/episodes.json",
        "GOOAYE_ARCHIVE_EPISODES_URL": base_url + "/episodes/",
    }
    try:
        first = run_cli(["download", "--episode", "691"], env=env)
        snapshot_path = work_dir / "episode-sources/EP0691/snapshot.json"
        transcript_path = work_dir / "episode-sources/EP0691/transcript.md"

        assert first.returncode == 0, first.stderr
        assert "EP691" in first.stdout
        assert "created" in first.stdout
        assert "youtube_id: J-e9oxqLzpc" in first.stdout
        assert "duration_seconds: 2995" in first.stdout
        assert "verification: OK" in first.stdout
        assert snapshot_path.is_file()
        assert transcript_path.is_file()
        before = (snapshot_path.read_bytes(), transcript_path.read_bytes())

        second = run_cli(["download", "--episode", "691"], env=env)

        assert second.returncode == 0, second.stderr
        assert "unchanged" in second.stdout
        assert before == (snapshot_path.read_bytes(), transcript_path.read_bytes())
        assert not (tmp_path / "gooaye-youtube-notes").exists()
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_doctor_reports_repository_statistics_without_private_synthesizer_maps(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    channel_path = tmp_path / "channel.json"
    archive_path = tmp_path / "episodes.json"
    transcript_dir = tmp_path / "full-transcripts"
    cache_dir = tmp_path / "grounded-headings"
    channel_path.write_text("{}", encoding="utf-8")
    archive_path.write_text("[]", encoding="utf-8")
    transcript_dir.mkdir()
    cache_dir.mkdir()

    class FakeRepository:
        legacy_channel_count = 1
        legacy_archive_count = 1
        legacy_transcript_count = 1
        normalized_snapshot_count = 1
        invalid_snapshot_count = 0

    class FakeSynthesizer:
        source_repository = FakeRepository()
        episode_numbers = [1, 691]

        def __init__(self) -> None:
            self.channel_path = channel_path
            self.archive_path = archive_path
            self.transcript_dir = transcript_dir
            self.cache_dir = cache_dir

    monkeypatch.setattr(cli, "EpisodeNoteSynthesizer", FakeSynthesizer)

    cli.cmd_doctor(Namespace())
    output = capsys.readouterr().out

    assert "Channel index: Found 1 entries" in output
    assert "Archive source: Found 1 entries" in output
    assert "Normalized snapshots: Found 1 verified snapshots" in output
    assert "Common valid episode count: 2" in output


def test_download_passes_the_archive_site_base_to_the_repository(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)
            self.snapshot_root = Path("/tmp/episode-sources")

    class FakeAcquirer:
        def __init__(self, **kwargs: object) -> None:
            captured["repository"] = kwargs["repository"]

        def acquire(self, number: int, force: bool) -> SimpleNamespace:
            return SimpleNamespace(
                number=number,
                status="created",
                youtube_id="J-e9oxqLzpc",
                duration_seconds=2995,
                snapshot_path="/tmp/episode-sources/EP0691",
            )

    monkeypatch.setenv("GOOAYE_ARCHIVE_EPISODES_URL", "https://archive.test/episodes/")
    monkeypatch.setattr(cli, "EpisodeSourceRepository", FakeRepository)
    monkeypatch.setattr(cli, "EpisodeAcquirer", FakeAcquirer)

    cli.cmd_download(Namespace(episode=691, latest=False, force=False))

    assert captured["archive_base_url"] == "https://archive.test/"
