from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from cold_transcript_exporter import (
    export_all,
    export_episode,
    format_cold_transcript,
    render_readme_index,
    sync_cold_transcript,
    update_archive_index,
)
from domain import EpisodeMetadata


def make_sample_metadata(number: int = 1) -> EpisodeMetadata:
    return EpisodeMetadata(
        number=number,
        youtube_id="vid_123",
        youtube_url="https://www.youtube.com/watch?v=vid_123",
        youtube_title=f"EP{number} | Raw Title",
        display_title=f"Curated Title {number}",
        date="2020-02-27",
        date_source="transcript_archive",
        duration_str="23:45",
        duration_seconds=1425,
        archive_url="https://whatmkreallysaid.com/episodes/EP1.md",
        summary="Summary of episode",
    )


def test_format_cold_transcript_contains_frontmatter_and_strips_top_h1() -> None:
    meta = make_sample_metadata(1)
    raw_transcript = (
        "# EP1 Curated Title 1\n\n"
        "歡迎收聽股癌，我是謝孟恭。\n\n"
        "## 贊助\n\n"
        "業配內容。"
    )
    formatted = format_cold_transcript(meta, raw_transcript)

    assert formatted.startswith("---\nepisode: 1\n")
    assert 'title: "Curated Title 1"' in formatted
    assert 'youtube_url: "https://www.youtube.com/watch?v=vid_123"' in formatted
    assert 'source: "whatmkreallysaid.com"' in formatted
    assert "# EP1｜Curated Title 1" in formatted
    # Top redundant H1 from raw transcript should be stripped
    assert "# EP1 Curated Title 1\n" not in formatted
    # Inner H2 should remain
    assert "## 贊助" in formatted
    assert "歡迎收聽股癌，我是謝孟恭。" in formatted


def test_render_readme_index_generates_markdown_table() -> None:
    episodes = [make_sample_metadata(1), make_sample_metadata(2)]
    content = render_readme_index(episodes)

    assert "# 股癌 (Gooaye) 完整逐字稿永久封存庫" in content
    assert "EP0001 - EP0002" in content
    assert "| EP0001 | 2020-02-27 | 23:45 | Curated Title 1 | [EP0001.md](EP0001.md) |" in content
    assert "| EP0002 | 2020-02-27 | 23:45 | Curated Title 2 | [EP0002.md](EP0002.md) |" in content


def test_export_episode_and_index_lifecycle(tmp_path: Path) -> None:
    repo = MagicMock()
    repo.episode_numbers = [1, 2]
    repo.get_metadata.side_effect = lambda n: make_sample_metadata(n)
    repo.load_transcript.side_effect = lambda n: f"Transcript for episode {n}."

    out_file = export_episode(1, repo, tmp_path)
    assert out_file.is_file()
    assert out_file.name == "EP0001.md"
    assert "Transcript for episode 1." in out_file.read_text(encoding="utf-8")

    index_file = update_archive_index(repo, tmp_path)
    assert index_file.is_file()
    assert "EP0001" in index_file.read_text(encoding="utf-8")


def test_sync_cold_transcript_skips_when_dir_missing(tmp_path: Path) -> None:
    missing_dir = tmp_path / "non_existent"
    repo = MagicMock()
    result = sync_cold_transcript(1, repo, missing_dir)
    assert result is None
    repo.load_transcript.assert_not_called()


def test_sync_cold_transcript_writes_when_dir_exists(tmp_path: Path) -> None:
    repo = MagicMock()
    repo.episode_numbers = [1]
    repo.get_metadata.return_value = make_sample_metadata(1)
    repo.load_transcript.return_value = "Verbatim content."

    result = sync_cold_transcript(1, repo, tmp_path)
    assert result is not None
    assert result.is_file()
    assert (tmp_path / "EP0001.md").is_file()
    assert (tmp_path / "README.md").is_file()
