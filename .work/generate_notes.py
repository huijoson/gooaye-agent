#!/usr/bin/env python3
"""Retired summary-note writer; pure rendering helpers remain for compatibility."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
CHANNEL_URL = "https://www.youtube.com/@Gooaye/videos"
ARCHIVE_URL = "https://whatmkreallysaid.com/"


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def episode_number(title: str) -> int | None:
    match = re.search(r"\bEP\s*(\d+)\b", title, re.IGNORECASE)
    return int(match.group(1)) if match else None


def format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "未知"
    seconds = round(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def format_upload_date(entry: dict, archive: dict) -> str:
    raw = entry.get("upload_date")
    if raw and re.fullmatch(r"\d{8}", str(raw)):
        return datetime.strptime(str(raw), "%Y%m%d").date().isoformat()
    timestamp = entry.get("timestamp") or entry.get("release_timestamp")
    if timestamp:
        return datetime.fromtimestamp(timestamp).date().isoformat()
    if archive.get("date"):
        return archive["date"]

    # Flat playlist metadata omits upload dates. Query results for exceptional
    # records are cached locally so regeneration remains deterministic.
    metadata_path = ROOT / ".work/samples" / f"{entry.get('id')}.metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        raw = metadata.get("upload_date")
        if raw and re.fullmatch(r"\d{8}", str(raw)):
            return datetime.strptime(str(raw), "%Y%m%d").date().isoformat()
        if metadata.get("timestamp"):
            return datetime.fromtimestamp(metadata["timestamp"]).date().isoformat()
    return "未知"


def split_chapters(summary: str) -> list[str]:
    """Split an already-curated summary into ordered conceptual chapters."""
    text = re.sub(r"\s+", " ", summary).strip()
    # Topic-transition markers often carry more meaning than a comma but may
    # not start a new sentence in the source summary.
    text = re.sub(
        r"(?<!^)(?=(?:市場端|產業端|操作面|投資面|總經面))",
        "\n",
        text,
    )
    parts = re.split(r"(?<=[。！？])\s*|[；;]\s*|\n+", text)
    parts = [part.strip(" ，、。；;：:") for part in parts if part.strip(" ，、。；;：:")]

    # A few curated summaries are one long sentence. Split those near the
    # midpoint on Chinese list punctuation rather than leaving an entire
    # episode as one oversized chapter.
    if len(parts) == 1 and len(parts[0]) >= 60:
        clauses = [clause.strip() for clause in re.split(r"[，、]", parts[0]) if clause.strip()]
        if len(clauses) >= 2:
            midpoint = max(1, len(clauses) // 2)
            parts = ["、".join(clauses[:midpoint]), "、".join(clauses[midpoint:])]

    # Keep notes readable: combine overflow fragments into the sixth chapter.
    if len(parts) > 6:
        parts = parts[:5] + ["；".join(parts[5:])]
    return parts or [text]


def chapter_heading(text: str, index: int, used: set[str]) -> str:
    cleaned = re.sub(
        r"^(?:本集|這集|本期)?(?:節目)?(?:先|再|也|主要)?(?:聊了|聊|談到|談論|討論|分享|深入討論|解析|剖析|提到|從)",
        "",
        text,
    ).strip(" ，、。；;：:-—")
    cleaned = re.sub(r"^(?:以及|並且|另外|另有|同時|接著|最後|而且|但|不過)", "", cleaned).strip()
    first = re.split(r"[，,：:；;]", cleaned, maxsplit=1)[0].strip()
    heading = first or f"主題 {index}"
    if len(heading) > 28:
        heading = heading[:27].rstrip() + "…"
    base = heading
    suffix = 2
    while heading in used:
        heading = f"{base}（{suffix}）"
        suffix += 1
    used.add(heading)
    return heading


def archive_episode_url(archive: dict) -> str:
    return f"{ARCHIVE_URL}episode.html?file={quote(archive['filename'])}"


def render_episode(number: int, entry: dict, archive: dict) -> str:
    youtube_id = entry["id"]
    youtube_url = f"https://www.youtube.com/watch?v={youtube_id}"
    date = format_upload_date(entry, archive)
    duration = format_duration(entry.get("duration"))
    original_title = entry.get("title") or f"EP{number}"
    display_title = archive.get("display_title") or archive.get("title") or original_title
    summary = archive["summary"].strip()
    chapters = split_chapters(summary)
    used_headings: set[str] = set()
    chapter_markdown = []
    for index, chapter in enumerate(chapters, 1):
        heading = chapter_heading(chapter, index, used_headings)
        chapter_markdown.append(f"### {index}. {heading}\n\n{chapter}。")

    return f"""---
episode: {number}
title: {yaml_string(display_title)}
youtube_title: {yaml_string(original_title)}
youtube_id: {yaml_string(youtube_id)}
youtube_url: {yaml_string(youtube_url)}
published: {yaml_string(date)}
duration: {yaml_string(duration)}
---

# EP{number}｜{display_title}

- **YouTube 原始標題：** {original_title}
- **發布日期：** {date}
- **片長：** {duration}
- **影片：** [YouTube]({youtube_url})

## 本集摘要

{summary}

## 章節觀念

{chr(10).join(chr(10) + chapter for chapter in chapter_markdown)}

## 資料來源與提醒

- 影片資訊：[Gooaye 股癌 YouTube]({youtube_url})
- 內容依據：[公開非官方逐字稿索引]({archive_episode_url(archive)})
- 本文整理的是依內容順序排列的「觀念章節」，不是影片精確時間碼。
- 逐字稿由 AI 聽寫並經第三方修正，專有名詞仍可能有誤；請以原始音訊為準。
- 本文僅整理節目內容，不構成投資建議。
"""


def render_readme(rows: list[dict], total_seconds: int) -> str:
    hours = total_seconds / 3600
    years = sorted({row["date"][:4] for row in rows if re.match(r"\d{4}-", row["date"])})
    return f"""# Gooaye 股癌 YouTube 全集章節觀念整理

本資料夾收錄 **{len(rows)} 支目前公開的 YouTube 影片**，涵蓋 EP1–EP690（YouTube 公開清單沒有 EP232），合計約 **{hours:.1f} 小時**。每集各有一份 Markdown，包含來源資訊、本集摘要與依內容順序整理的觀念章節。

- [全集索引](_index.md)
- [逐集筆記](episodes/)
- 頻道：[{CHANNEL_URL}]({CHANNEL_URL})
- 年份範圍：{years[0]}–{years[-1]}

## 檔案格式

每份 `episodes/EPxxxx.md` 包含：

1. YAML metadata（集數、標題、YouTube ID、網址、日期、片長）
2. 本集摘要
3. 依討論順序拆分的章節觀念
4. YouTube 與內容依據連結

## 整理方式與限制

- YouTube 頻道沒有可用的手動或自動字幕，因此內容依據採用公開的非官方股癌逐字稿索引，再和 YouTube 影片 ID、標題、日期及片長逐集核對。
- 這些章節是**主題/觀念章節**，不是精確時間碼；沒有從內容推測或虛構時間點。
- 公開 YouTube 清單共有 {len(rows)} 支，集數缺 EP232；索引只收錄實際可由該頻道公開清單取得的影片。
- AI 逐字稿、摘要與專有名詞可能有誤，正確內容仍應以原始影片為準。
- 所有內容僅供學習與索引，不構成投資建議。

產生日期：{datetime.now().date().isoformat()}
"""


def render_index(rows: list[dict]) -> str:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in sorted(rows, key=lambda item: item["number"], reverse=True):
        grouped[row["date"][:4] if re.match(r"\d{4}-", row["date"]) else "日期未知"].append(row)

    sections = [
        "# 全集索引",
        "",
        f"共 {len(rows)} 支 YouTube 公開影片。章節為主題順序，非精確時間碼。",
        "",
        "| 年份 | 集數 |",
        "|---:|---:|",
    ]
    for year in sorted(grouped, reverse=True):
        sections.append(f"| {year} | {len(grouped[year])} |")

    for year in sorted(grouped, reverse=True):
        sections.extend(["", f"## {year}", "", "| 集數 | 日期 | 片長 | 標題 | YouTube |", "|---:|:---:|---:|---|:---:|"])
        for row in grouped[year]:
            title = row["title"].replace("|", "\\|").replace("\n", " ")
            sections.append(
                f"| [EP{row['number']}](episodes/EP{row['number']:04d}.md) | "
                f"{row['date']} | {row['duration']} | {title} | "
                f"[觀看](https://www.youtube.com/watch?v={row['youtube_id']}) |"
            )
    sections.append("")
    return "\n".join(sections)


def main() -> None:
    raise SystemExit(
        "generate_notes.py is retired: use `python3 .work/cli.py publish --output-dir PATH` "
        "for a formal publication or `synthesize --output-dir PATH` for an isolated Preview."
    )


if __name__ == "__main__":
    main()
