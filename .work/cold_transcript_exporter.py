"""Cold transcript archive export and synchronization."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from domain import EpisodeMetadata, yaml_string
from episode_source_repository import EpisodeSourceRepository

DEFAULT_TRANSCRIPTS_DIR_NAME = "transcripts"


def format_cold_transcript(meta: EpisodeMetadata, raw_transcript: str) -> str:
    """Format an episode's verbatim transcript with standard YAML frontmatter."""
    lines = raw_transcript.strip().splitlines()
    body_lines: list[str] = []
    skipped_h1 = False
    for line in lines:
        if not skipped_h1 and line.strip().startswith("# "):
            skipped_h1 = True
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip()

    fm_lines = [
        "---",
        f"episode: {meta.number}",
        f"title: {yaml_string(meta.display_title)}",
        f"youtube_title: {yaml_string(meta.youtube_title)}",
        f"youtube_id: {yaml_string(meta.youtube_id)}",
        f"youtube_url: {yaml_string(meta.youtube_url)}",
        f"episode_date: {yaml_string(meta.date)}",
        f"duration: {yaml_string(meta.duration_str)}",
        f"source: {yaml_string('whatmkreallysaid.com')}",
        "---",
        "",
        f"# EP{meta.number}｜{meta.display_title}",
        "",
        f"- **YouTube 原始標題：** {meta.youtube_title}",
        f"- **節目日期：** {meta.date}",
        f"- **片長：** {meta.duration_str}",
    ]
    if meta.youtube_url:
        fm_lines.append(f"- **影片：** [YouTube]({meta.youtube_url})")
    if meta.archive_url:
        fm_lines.append(f"- **來源存檔：** [whatmkreallysaid.com]({meta.archive_url})")
    fm_lines.extend(["", "---", "", body, ""])
    return "\n".join(fm_lines)


def render_readme_index(episodes: Sequence[EpisodeMetadata]) -> str:
    """Render the master markdown index table for all episodes in the cold archive."""
    if not episodes:
        return "# 股癌 (Gooaye) 完整逐字稿永久封存庫\n\n尚無集數。\n"

    first_ep = episodes[0]
    last_ep = episodes[-1]
    lines = [
        "# 股癌 (Gooaye) 完整逐字稿永久封存庫 (Cold Transcript Archive)",
        "",
        "本目錄為獨立永久封存的股癌 (Gooaye) Podcast 完整逐字稿集合，旨在作為防範外部非官方逐字稿網站（如 whatmkreallysaid.com）未來可能下線或資料失聯的獨立冷備份存檔層。",
        "",
        f"- **總集數：** {len(episodes)} 集 (EP{first_ep.number:04d} - EP{last_ep.number:04d})",
        f"- **涵蓋時間：** {first_ep.date} 至 {last_ep.date}",
        "- **規格：** 包含標準 YAML Frontmatter 元數據與 100% 原始完整逐字內容",
        "- **存放定位：** 獨立於 `.work/` 處理管線與 `gooaye-youtube-notes/` 雙層導航筆記發布目錄之外",
        "",
        "## 集數索引表",
        "",
        "| 集數 | 節目日期 | 片長 | 標題 | 逐字稿連結 | 原始影片 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for m in episodes:
        yt_link = f"[YouTube]({m.youtube_url})" if m.youtube_url else "-"
        lines.append(
            f"| EP{m.number:04d} | {m.date} | {m.duration_str} | {m.display_title} | [EP{m.number:04d}.md](EP{m.number:04d}.md) | {yt_link} |"
        )
    lines.append("")
    return "\n".join(lines)


def export_episode(
    number: int,
    repository: EpisodeSourceRepository,
    output_dir: Path,
) -> Path:
    """Export a single episode's full transcript to the cold archive."""
    meta = repository.get_metadata(number)
    transcript = repository.load_transcript(number)
    content = format_cold_transcript(meta, transcript)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"EP{number:04d}.md"
    out_file.write_text(content, encoding="utf-8")
    return out_file


def update_archive_index(
    repository: EpisodeSourceRepository,
    output_dir: Path,
) -> Path:
    """Regenerate README.md index table for all episodes found in repository."""
    episodes: list[EpisodeMetadata] = []
    for num in repository.episode_numbers:
        episodes.append(repository.get_metadata(num))
    episodes.sort(key=lambda m: m.number)

    index_file = output_dir / "README.md"
    content = render_readme_index(episodes)
    index_file.write_text(content, encoding="utf-8")
    return index_file


def export_all(
    repository: EpisodeSourceRepository,
    output_dir: Path,
) -> int:
    """Export all available episodes and generate README.md index table."""
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    episodes: list[EpisodeMetadata] = []
    for num in repository.episode_numbers:
        meta = repository.get_metadata(num)
        episodes.append(meta)
        transcript = repository.load_transcript(num)
        content = format_cold_transcript(meta, transcript)
        out_file = output_dir / f"EP{num:04d}.md"
        out_file.write_text(content, encoding="utf-8")
        count += 1

    episodes.sort(key=lambda m: m.number)
    index_file = output_dir / "README.md"
    index_file.write_text(render_readme_index(episodes), encoding="utf-8")
    return count


def sync_cold_transcript(
    number: int,
    repository: EpisodeSourceRepository,
    transcripts_dir: Path,
) -> Path | None:
    """Conditionally sync episode transcript to cold archive if transcripts_dir exists."""
    if not transcripts_dir.exists():
        return None
    if not hasattr(repository, "get_metadata") or not hasattr(repository, "load_transcript"):
        return None
    out_file = export_episode(number, repository, transcripts_dir)
    update_archive_index(repository, transcripts_dir)
    return out_file

