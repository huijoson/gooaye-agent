"""Markdown renderer - Formats domain objects into standard markdown notes, index, and readme documents."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Sequence

from domain import EpisodeNote, SynthesisSummary

CHANNEL_URL = "https://www.youtube.com/@Gooaye/videos"


class MarkdownRenderer:
    """Renders structured domain notes and indices to standardized Markdown strings."""

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

        return f"""# Gooaye 股癌 YouTube 全集章節觀念整理

本資料夾收錄 **{len(notes)} 支目前公開的 YouTube 影片**，涵蓋 EP1–EP690（YouTube 公開清單沒有 EP232），合計約 **{hours:.1f} 小時**。全集共 **{summary.total_chapters:,} 章**、**{2 * summary.total_chapters:,} 條逐字稿摘錄**；每集各有一份 Markdown，以完整逐字稿為內容依據，整理成依討論順序排列的章節觀念。

- [全集索引](_index.md)
- [逐集筆記](episodes/)
- 頻道：[{channel_url}]({channel_url})
- 年份範圍：{year_range}
- 章節分布：{dist_str}

## 檔案格式

每份 `episodes/EPxxxx.md` 包含 YAML metadata、YouTube 原始資訊、3–6 個觀念章節，以及來源與方法說明。每章兩個條列均取自完整逐字稿中的相關段落，並限制為短篇摘錄，方便回查原音。頁首使用的 `display_title`／策展標題來自第三方逐字稿索引，YouTube 原始標題則獨立保留於 metadata 與內文。

## 整理方式與限制

- YouTube 頻道沒有可用的手動或自動字幕；本資料使用公開非官方逐字稿網站提供的**完整逐字稿**。該站說明內容由 AI 聽寫並經人工修正。
- 第三方 `summary` 欄位只用來搜尋全文中的候選主題，**沒有原文複製成「本集摘要」**；實際章節條列來自完整逐字稿，而非把摘要按標點拆段。
- 各章標題由該章入選的兩段完整逐字稿摘錄重新命名：命名模型的輸入不含第三方 `summary`；`summary` 只在產生後用來拒絕撞句，少數未通過自動驗證者由人工直接依兩段摘錄覆核。章序依入選摘錄在逐字稿中的實際位置排列。
- 這些章節是主題／觀念索引，不是精確時間碼。
- 日期主要來自第三方逐字稿索引，不宣稱已逐集核對 YouTube 上傳日期；唯一缺日期的 EP162 使用單支 YouTube metadata 補為 2021-07-31。
- 公開 YouTube 清單共有 {len(notes)} 支，集數缺 EP232；只收錄實際出現在頻道公開清單中的影片。
- 非官方逐字稿與抽取結果可能有聽寫或專有名詞錯誤，正確內容以原始影片為準。
- 所有內容僅供學習與索引，不構成投資建議。

產生日期：{datetime.now().date().isoformat()}
"""

    @staticmethod
    def render_index(
        notes: Sequence[EpisodeNote],
        summary: SynthesisSummary,
    ) -> str:
        """Render the _index.md directory file."""
        grouped: dict[str, list[EpisodeNote]] = defaultdict(list)
        for note in sorted(notes, key=lambda n: n.metadata.number, reverse=True):
            year = note.metadata.date[:4] if re.match(r"\d{4}-", note.metadata.date) else "日期未知"
            grouped[year].append(note)

        lines = [
            "# 全集索引",
            "",
            f"共 {len(notes)} 支 YouTube 公開影片、{summary.total_chapters:,} 章、{2 * summary.total_chapters:,} 條逐字稿摘錄；涵蓋 EP1–EP690，公開清單唯一缺號為 EP232。章節按完整逐字稿內容順序編排，非精確時間碼。",
            "",
            "## 📚 主題專題深度指南 (Thematic Topic Guides)",
            "",
            "| 專題手冊 | 分類 | 說明 |",
            "|:---|:---:|:---|",
            "| [AI 伺服器、散熱、電力與 ASIC 自研晶片演進](topics/ai-hardware-and-semiconductor.md) | 產業與硬體架構 | 追蹤 2021 至 2026 年主委對水冷、CDU、800V 電力與 CSP 自研 ASIC 晶片之論述脈絡。 |",
            "| [主委投資心態、部位管理、停損紀律與期望值實戰守則](topics/investment-mindset-and-risk-control.md) | 投資心態與風險控制 | 彙整歷年部位控制、停損停利紀律、勝率/賠率期望值計算與生活化哲學。 |",
            "| [總體經濟循環、聯準會降息循環、房產與資產配置](topics/macro-cycle-and-asset-allocation.md) | 總體經濟與資產配置 | 整理景氣循環位階、聯準會利率政策、通膨、美股與房產資產配置。 |",
            "| [Apple 供應鏈、智慧型手機與消費性電子週期](topics/apple-and-consumer-electronics.md) | 消費性電子與供應鏈 | 探討 Apple 產品週期、台廠果鏈消長、折疊機與消費性電子拉貨動能。 |",
            "",
            "- 👉 [查看完整主題專題目錄與使用指引](topics/README.md)",
            "",
            "## 🗓️ 歷年集數大綱",
            "",
            "| 年份 | 集數 |",
            "|---:|---:|",
        ]
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
