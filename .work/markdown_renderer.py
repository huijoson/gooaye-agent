"""Markdown renderer - Formats domain objects into standard markdown notes, index, and readme documents."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Sequence

from domain import EpisodeNote, SynthesisSummary, TopicDefinition

CHANNEL_URL = "https://www.youtube.com/@Gooaye/videos"


class MarkdownRenderer:
    """Renders structured domain notes and indices to standardized Markdown strings."""

    @staticmethod
    def _corpus_ranges(notes: Sequence[EpisodeNote]) -> tuple[str, str]:
        numbers = [note.metadata.number for note in notes]
        chapter_counts = [len(note.chapters) for note in notes]
        episode_range = f"EP{min(numbers)}–EP{max(numbers)}" if numbers else "無集數"
        if not chapter_counts:
            chapter_range = "0"
        elif min(chapter_counts) == max(chapter_counts):
            chapter_range = str(chapter_counts[0])
        else:
            chapter_range = f"{min(chapter_counts)}–{max(chapter_counts)}"
        return episode_range, chapter_range

    @staticmethod
    def render_episode(note: EpisodeNote, mode: str = "slim") -> str:
        """Render a single EpisodeNote into its full Markdown file text."""
        return note.render_markdown(mode=mode)

    @staticmethod
    def render_readme(
        notes: Sequence[EpisodeNote],
        summary: SynthesisSummary,
        channel_url: str = CHANNEL_URL,
    ) -> str:
        """Render the top-level README.md for the notes directory."""
        hours = summary.total_seconds / 3600
        years = sorted({note.metadata.date[:4] for note in notes if re.match(r"\d{4}-", note.metadata.date)})
        dist_str = "、".join(f"{count} 章：{episodes} 集" for count, episodes in sorted(summary.chapter_distribution.items()))
        year_range = f"{years[0]}–{years[-1]}" if years else "2020–2026"
        episode_range, chapter_range = MarkdownRenderer._corpus_ranges(notes)

        asr_count = sum(bool(note.metadata.transcription) for note in notes)
        source_description = (
            f"- 完整逐字稿包含第三方封存文字，以及 {asr_count} 集官方節目音訊的自動語音轉錄。自動轉錄未經逐句人工校對，各集列有音訊與模型來源。"
            if asr_count else
            "- YouTube 頻道沒有可用的手動或自動字幕；本資料使用公開非官方逐字稿網站提供的**完整逐字稿**。該站說明內容由 AI 聽寫並經人工修正。"
        )
        title_description = (
            "頁首標題取自第三方逐字稿索引；自動轉錄集數則使用官方節目標題。YouTube 原始標題保留於 metadata 與內文。"
            if asr_count else
            "頁首使用的 `display_title`／策展標題來自第三方逐字稿索引，YouTube 原始標題則獨立保留於 metadata 與內文。"
        )
        date_description = (
            "- 第三方逐字稿日期依其索引；自動轉錄集數的日期使用官方節目 metadata。各集記錄日期來源。"
            if asr_count else
            "- 日期主要來自第三方逐字稿索引，不宣稱已逐集核對 YouTube 上傳日期；唯一缺日期的 EP162 使用單支 YouTube metadata 補為 2021-07-31。"
        )
        summary_description = (
            "- 第三方摘要僅用於對應集數的主題定位；自動轉錄集數使用來源標示提示。章節條列均從各集逐字稿抽取。"
            if asr_count else
            "第三方 `summary` 欄位只用來搜尋全文中的候選主題，**沒有原文複製成「本集摘要」**；實際章節條列來自完整逐字稿，而非把摘要按標點拆段。"
        )
        heading_description = (
            "- 章節標題與核心觀點依逐字稿摘錄整理；自動轉錄集數的摘錄按辨識分段建立，章序是內容索引而非精確時間碼。"
            if asr_count else
            "各章標題由該章入選的兩段完整逐字稿摘錄重新命名：命名模型的輸入不含第三方 `summary`；`summary` 只在產生後用來拒絕撞句，少數未通過自動驗證者由人工直接依兩段摘錄覆核。章序依入選摘錄在逐字稿中的實際位置排列。"
        )
        return f"""# Gooaye 股癌 YouTube 全集章節觀念整理

本資料夾收錄 **{len(notes)} 支目前公開的 YouTube 影片**，涵蓋 {episode_range}，合計約 **{hours:.1f} 小時**。全集共 **{summary.total_chapters:,} 章**、**{2 * summary.total_chapters:,} 條逐字稿摘錄**；每集各有一份 Markdown，以完整逐字稿為內容依據，整理成依討論順序排列的章節觀念。

- [全集索引](_index.md)
- [逐集筆記](episodes/)
- 頻道：[{channel_url}]({channel_url})
- 年份範圍：{year_range}
- 章節分布：{dist_str}

## 檔案格式

每份 `episodes/EPxxxx.md` 包含 YAML metadata、YouTube 原始資訊、{chapter_range} 個觀念章節，以及來源與方法說明。每章兩個條列均取自完整逐字稿中的相關段落，並限制為短篇摘錄，方便回查原音。{title_description}

## 整理方式與限制

{source_description}
{summary_description}
{heading_description}
- 這些章節是主題／觀念索引，不是精確時間碼。
{date_description}
- 公開 YouTube 清單共有 {len(notes)} 支，集數範圍為 {episode_range}；只收錄實際出現在頻道公開清單中的影片。
- 非官方逐字稿與抽取結果可能有聽寫或專有名詞錯誤，正確內容以原始影片為準。
- 所有內容僅供學習與索引，不構成投資建議。

產生日期：{datetime.now().date().isoformat()}
"""

    @staticmethod
    def render_index(
        notes: Sequence[EpisodeNote],
        summary: SynthesisSummary,
        topics: Sequence[TopicDefinition] = (),
    ) -> str:
        """Render the _index.md directory file."""
        episode_range, _ = MarkdownRenderer._corpus_ranges(notes)
        grouped: dict[str, list[EpisodeNote]] = defaultdict(list)
        for note in sorted(notes, key=lambda n: n.metadata.number, reverse=True):
            year = note.metadata.date[:4] if re.match(r"\d{4}-", note.metadata.date) else "日期未知"
            grouped[year].append(note)

        lines = [
            "# 全集索引",
            "",
            f"共 {len(notes)} 支 YouTube 公開影片、{summary.total_chapters:,} 章、{2 * summary.total_chapters:,} 條逐字稿摘錄；涵蓋 {episode_range}。章節按完整逐字稿內容順序編排，非精確時間碼。",
            "",
            "## 📚 主題專題深度指南 (Thematic Topic Guides)",
            "",
            "| 專題手冊 | 分類 | 說明 |",
            "|:---|:---:|:---|",
        ]
        lines.extend(
            f"| [{topic.title}](topics/{topic.slug}.md) | {topic.category} | {topic.description} |"
            for topic in topics
        )
        lines.extend([
            "",
            "- 👉 [查看完整主題專題目錄與使用指引](topics/README.md)",
            "",
            "## 🗓️ 歷年集數大綱",
            "",
            "| 年份 | 集數 |",
            "|---:|---:|",
        ])
        for year in sorted(grouped, reverse=True):
            lines.append(f"| {year} | {len(grouped[year])} |")

        for year in sorted(grouped, reverse=True):
            lines.extend(["", f"## {year}", "", "| 集數 | 日期 | 片長 | 章節 | 標題 | YouTube |", "|---:|:---:|---:|---:|---|:---:|"])
            for note in grouped[year]:
                title = note.metadata.display_title.replace("|", "\\|").replace("\n", " ")
                lines.append(
                    f"| [EP{note.metadata.number}](episodes/EP{note.metadata.number:04d}.md) | "
                    f"{note.metadata.date} | {note.metadata.duration_str} | {len(note.chapters)} | {title} | "
                    f"[觀看]({note.metadata.youtube_url}) |"
                )
        lines.append("")
        return "\n".join(lines)
