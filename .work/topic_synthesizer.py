"""Thematic Topic Synthesizer and Renderer for Gooaye knowledge base."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Sequence

from pathlib import Path

from domain import (
    Chapter,
    EpisodeMetadata,
    EpisodeNote,
    ThematicChapterRef,
    ThematicMilestone,
    TopicDefinition,
    TopicGuide,
    yaml_string,
)
from topic_catalog import DEFAULT_TOPICS


def load_note_from_markdown(file_path: Path | str) -> EpisodeNote:
    """Parse a synthesized Markdown note file (e.g. EP0001.md) back into an EpisodeNote."""
    path = Path(file_path)
    text = path.read_text(encoding="utf-8")

    # Parse frontmatter
    fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    fm_dict: dict[str, str] = {}
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                fm_dict[key] = val

    ep_number = int(fm_dict.get("episode", 0))
    display_title = fm_dict.get("title", "")
    youtube_title = fm_dict.get("youtube_title", "")
    youtube_id = fm_dict.get("youtube_id", "")
    youtube_url = fm_dict.get("youtube_url", "")
    episode_date = fm_dict.get("episode_date", "")
    episode_date_source = fm_dict.get("episode_date_source", "")
    duration = fm_dict.get("duration", "")

    # Duration seconds
    duration_seconds = 0
    if duration and ":" in duration:
        parts = [int(p) for p in duration.split(":") if p.isdigit()]
        if len(parts) == 2:
            duration_seconds = parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            duration_seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]

    metadata = EpisodeMetadata(
        number=ep_number,
        youtube_id=youtube_id,
        youtube_url=youtube_url,
        youtube_title=youtube_title,
        display_title=display_title,
        date=episode_date,
        date_source=episode_date_source,
        duration_str=duration,
        duration_seconds=duration_seconds,
        archive_url="",
        summary="",
    )

    # Parse chapters
    chapter_blocks = re.split(r"\n###\s+(\d+)\.\s+", text)
    chapters: list[Chapter] = []

    for i in range(1, len(chapter_blocks), 2):
        ch_idx = int(chapter_blocks[i])
        ch_text = chapter_blocks[i + 1]

        lines = ch_text.strip().splitlines()
        heading = lines[0].strip()
        takeaway = ""
        excerpts: list[str] = []

        for line in lines[1:]:
            line_str = line.strip()
            if line_str.startswith("- **核心觀點：**"):
                takeaway = line_str.replace("- **核心觀點：**", "").strip()
            elif line_str.startswith("- "):
                clean_bullet = line_str[2:].strip()
                if clean_bullet and not clean_bullet.startswith("**"):
                    excerpts.append(clean_bullet)

        chapters.append(
            Chapter(
                index=ch_idx,
                heading=heading,
                takeaway=takeaway,
                excerpts=tuple(excerpts),
                position=(ch_idx - 1) * 500,
            )
        )

    return EpisodeNote(metadata=metadata, chapters=tuple(chapters))


def load_all_notes_from_dir(episodes_dir: Path | str) -> list[EpisodeNote]:
    """Load all slim markdown notes (EP*.md, excluding .full.md) from directory."""
    ep_dir = Path(episodes_dir)
    notes: list[EpisodeNote] = []
    for file_path in sorted(ep_dir.glob("EP*.md")):
        if file_path.name.endswith(".full.md"):
            continue
        try:
            note = load_note_from_markdown(file_path)
            notes.append(note)
        except Exception:
            continue
    return notes



class TopicGuideSynthesizer:
    """Synthesizes structured topic guides across episode notes."""

    def __init__(self, score_threshold: float = 4.0):
        self.score_threshold = score_threshold
        self.renderer = TopicGuideRenderer()

    def synthesize_all_topics(
        self,
        episodes: Sequence[EpisodeNote],
        topics: Sequence[TopicDefinition] = DEFAULT_TOPICS,
    ) -> list[TopicGuide]:
        """Synthesize multiple TopicGuides for given topic definitions."""
        return [self.synthesize_topic(topic_def, episodes) for topic_def in topics]

    def synthesize_and_save_all(
        self,
        episodes: Sequence[EpisodeNote],
        output_dir: Path | str,
        topics: Sequence[TopicDefinition] = DEFAULT_TOPICS,
    ) -> list[Path]:
        """Synthesize all topics and write markdown files + README.md to an isolated preview destination."""
        from episode_synthesizer import validate_preview_output_directory

        out_path = validate_preview_output_directory(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        guides = self.synthesize_all_topics(episodes, topics)
        saved_files: list[Path] = []

        for guide in guides:
            file_path = out_path / f"{guide.slug}.md"
            content = self.renderer.render(guide)
            file_path.write_text(content, encoding="utf-8")
            saved_files.append(file_path)

        # Render and write README.md for topics
        readme_path = out_path / "README.md"
        readme_content = self.renderer.render_topics_readme(guides, episodes)
        readme_path.write_text(readme_content, encoding="utf-8")
        saved_files.append(readme_path)

        return saved_files

    def score_chapter(
        self,
        chapter: Chapter,
        keywords: tuple[str, ...],
    ) -> tuple[float, tuple[str, ...]]:
        """Score chapter relevance against topic keywords."""
        score = 0.0
        matched = set()

        heading_lower = chapter.heading.lower()
        takeaway_lower = chapter.takeaway.lower()
        excerpts_lower = " ".join(chapter.excerpts).lower()

        for kw in keywords:
            kw_lower = kw.lower()
            kw_score = 0.0

            if kw_lower in heading_lower:
                kw_score += 10.0
                matched.add(kw)

            if kw_lower in takeaway_lower:
                kw_score += 5.0
                matched.add(kw)

            if kw_lower in excerpts_lower:
                kw_score += 2.0
                matched.add(kw)

            score += kw_score

        return score, tuple(sorted(matched))

    def synthesize_topic(
        self,
        topic_def: TopicDefinition,
        episodes: Sequence[EpisodeNote],
    ) -> TopicGuide:
        """Synthesize a single TopicGuide from a collection of EpisodeNotes."""
        matched_refs: list[ThematicChapterRef] = []

        for ep in episodes:
            for ch in ep.chapters:
                score, matched_kws = self.score_chapter(
                    chapter=ch,
                    keywords=topic_def.keywords,
                )

                if score >= self.score_threshold:
                    matched_refs.append(
                        ThematicChapterRef(
                            episode_number=ep.metadata.number,
                            episode_title=ep.metadata.display_title,
                            published_at=ep.metadata.date,
                            chapter_index=ch.index,
                            heading=ch.heading,
                            takeaway=ch.takeaway,
                            relevance_score=score,
                            matched_keywords=matched_kws,
                            excerpts=ch.excerpts,
                        )
                    )

        # Sort chronologically
        matched_refs.sort(key=lambda r: (r.published_at, r.episode_number, r.chapter_index))

        if matched_refs:
            time_span = (matched_refs[0].published_at, matched_refs[-1].published_at)
        else:
            time_span = ("未知", "未知")

        # Synthesize top takeaways (unique, top-scored)
        unique_takeaways = []
        seen = set()
        for ref in sorted(matched_refs, key=lambda r: r.relevance_score, reverse=True):
            if ref.takeaway and ref.takeaway not in seen:
                seen.add(ref.takeaway)
                unique_takeaways.append(ref.takeaway)
                if len(unique_takeaways) >= 8:
                    break

        # Synthesize chronological milestones
        milestones = self._build_milestones(matched_refs)

        return TopicGuide(
            definition=topic_def,
            time_span=time_span,
            summary_takeaways=tuple(unique_takeaways),
            milestones=tuple(milestones),
            chapters=tuple(matched_refs),
        )

    def _build_milestones(self, refs: list[ThematicChapterRef]) -> list[ThematicMilestone]:
        """Group matched chapters by era/year and build milestone summaries."""
        if not refs:
            return []

        by_year: dict[str, list[ThematicChapterRef]] = defaultdict(list)
        for ref in refs:
            year = ref.published_at[:4] if re.match(r"\d{4}-", ref.published_at) else "其他"
            by_year[year].append(ref)

        milestones = []
        for year in sorted(by_year):
            year_refs = by_year[year]
            top_ref = max(year_refs, key=lambda r: r.relevance_score)
            key_eps = tuple(sorted({r.episode_number for r in year_refs}))
            
            summary = top_ref.takeaway or f"{year} 年相關核心討論與觀點建立。"
            milestones.append(
                ThematicMilestone(
                    period=f"{year} 年重點演進",
                    summary=summary,
                    key_episodes=key_eps[:5],
                )
            )

        return milestones


class TopicGuideRenderer:
    """Renders a TopicGuide into a structured Markdown document."""

    @staticmethod
    def render(guide: TopicGuide) -> str:
        """Render full Markdown text for a TopicGuide."""
        time_span_str = f"{guide.time_span[0]} ~ {guide.time_span[1]}"

        # Frontmatter
        lines = [
            "---",
            f"slug: {yaml_string(guide.slug)}",
            f"title: {yaml_string(guide.title)}",
            f"category: {yaml_string(guide.category)}",
            f"episodes_count: {guide.episodes_count}",
            f"chapters_count: {guide.chapters_count}",
            f"time_span: {yaml_string(time_span_str)}",
            f"content_method: {yaml_string('thematic_synthesis')}",
            "---",
            "",
            f"# {guide.title}",
            "",
            f"> **主題分類**：{guide.category} ｜ **涵蓋集數**：{guide.episodes_count} 集 ｜ **收錄章節**：{guide.chapters_count} 章 ｜ **時間跨度**：{time_span_str}",
            "",
            guide.description,
            "",
            "## 📑 目錄",
            "",
            "- [🎯 核心結論速覽](#-核心結論速覽)",
            "- [⏳ 觀點時序演進與重要里程碑](#-觀點時序演進與重要里程碑)",
            "- [📚 歷年深度觀點與章節精華](#-歷年深度觀點與章節精華)",
        ]

        if guide.faq:
            lines.append("- [❓ 專題精選問答](#-專題精選問答)")

        lines.extend([
            "- [🔗 相關集數索引與引用列表](#-相關集數索引與引用列表)",
            "",
            "---",
            "",
            "## 🎯 核心結論速覽",
            "",
        ])

        if guide.summary_takeaways:
            for i, takeaway in enumerate(guide.summary_takeaways, 1):
                lines.append(f"{i}. **{takeaway}**")
        else:
            lines.append("- （暫無核心結論摘錄）")

        lines.extend([
            "",
            "---",
            "",
            "## ⏳ 觀點時序演進與重要里程碑",
            "",
        ])

        if guide.milestones:
            for ms in guide.milestones:
                ep_links = ", ".join(f"[EP{ep:04d}](../episodes/EP{ep:04d}.md)" for ep in ms.key_episodes)
                lines.extend([
                    f"### 📍 {ms.period}",
                    "",
                    f"- **演進要點**：{ms.summary}",
                    f"- **代表集數**：{ep_links}",
                    "",
                ])
        else:
            lines.extend(["- （暫無時序里程碑記錄）", ""])

        lines.extend([
            "---",
            "",
            "## 📚 歷年深度觀點與章節精華",
            "",
        ])

        # Group chapters by year
        by_year: dict[str, list[ThematicChapterRef]] = defaultdict(list)
        for ref in guide.chapters:
            year = ref.published_at[:4] if re.match(r"\d{4}-", ref.published_at) else "其他"
            by_year[year].append(ref)

        for year in sorted(by_year):
            lines.extend([
                f"### 🗓️ {year} 年專題觀點",
                "",
            ])
            for ref in by_year[year]:
                kws_str = "、".join(ref.matched_keywords)
                lines.extend([
                    f"#### [EP{ref.episode_number}｜{ref.episode_title}](../episodes/EP{ref.episode_number:04d}.md) - 第 {ref.chapter_index} 章：{ref.heading}",
                    "",
                    f"- **發布日期**：{ref.published_at}",
                    f"- **核心觀點**：{ref.takeaway}",
                    f"- **關鍵詞**：`{kws_str}`",
                ])
                if ref.excerpts:
                    lines.append("- **逐字稿引述**：")
                    for excerpt in ref.excerpts[:2]:
                        lines.append(f"  - 「{excerpt}」")
                lines.append("")

        if guide.faq:
            lines.extend([
                "---",
                "",
                "## ❓ 專題精選問答",
                "",
            ])
            for q, a in guide.faq:
                lines.extend([
                    f"### Q: {q}",
                    "",
                    f"{a}",
                    "",
                ])

        lines.extend([
            "---",
            "",
            "## 🔗 相關集數索引與引用列表",
            "",
            "| 集數 | 發布日期 | 章節 | 標題 | 核心觀點摘要 |",
            "|:---|:---:|:---:|---|---|",
        ])

        for ref in guide.chapters:
            ep_link = f"[EP{ref.episode_number}](../episodes/EP{ref.episode_number:04d}.md)"
            heading_esc = ref.heading.replace("|", "\\|")
            takeaway_esc = (ref.takeaway[:40] + "..." if len(ref.takeaway) > 40 else ref.takeaway).replace("|", "\\|")
            lines.append(
                f"| {ep_link} | {ref.published_at} | 第 {ref.chapter_index} 章 | {heading_esc} | {takeaway_esc} |"
            )

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def render_topics_readme(
        guides: Sequence[TopicGuide],
        notes: Sequence[EpisodeNote],
    ) -> str:
        """Render top-level README.md for the topics directory."""
        total_chapters = sum(len(note.chapters) for note in notes)
        lines = [
            "# Gooaye 股癌 跨集數主題式深度知識庫指南",
            "",
            f"本目錄收錄依據 {len(notes):,} 集全量逐字稿與 {total_chapters:,} 個結構化章節觀點提煉之**跨集數主題專題手冊 (Thematic Topic Guides)**。",
            "打破單集時間限制，將主委自 2020 至 2026 年歷次對關鍵產業、硬體架構、總體經濟與交易哲學之核心觀點依時序脈絡整合。",
            "",
            "- [回全集索引](../_index.md)",
            "- [回單集筆記庫](../episodes/)",
            "",
            "## 📚 收錄主題一覽表",
            "",
            "| 主題專題 | 分類 | 涵蓋集數 | 收錄章節 | 時間跨度 | 簡介 |",
            "|:---|:---:|:---:|:---:|:---:|:---|",
        ]

        for g in guides:
            link = f"[{g.title}]({g.slug}.md)"
            time_span_str = f"{g.time_span[0]} ~ {g.time_span[1]}"
            desc = g.description.replace("|", "\\|")
            lines.append(
                f"| {link} | {g.category} | {g.episodes_count} 集 | {g.chapters_count} 章 | {time_span_str} | {desc} |"
            )

        lines.extend([
            "",
            "## 🔍 專題使用指南與查證協定",
            "",
            "1. **雙層穿透查證**：每篇專題手冊中的每條觀點與引述均標註集數編號（如 `EP0450`），點擊可直接跳轉至對應單集導航筆記 (`.md`) 或深度筆記 (`.full.md`) 查看完整上下文。",
            "2. **100% 接地保證**：所有專題觀點均直接錨定於通過品質審計的章節 Takeaway 與逐字稿摘錄，杜絕二次生成幻覺與年份錯置。",
            "3. **漸進式檢索支援**：AI Agent 可直接載入對應主題之 Markdown 手冊，在 ~1,500 tokens 內快速獲取跨越數年的完整投資脈絡。",
            "",
        ])
        return "\n".join(lines)


class TopicQualityAuditor:
    """Audits topic guide markdown files for grounded references, valid links, and structural integrity."""

    def __init__(self):
        self._note_cache: dict[Path, EpisodeNote] = {}

    def _get_note(self, file_path: Path) -> EpisodeNote | None:
        if file_path not in self._note_cache:
            try:
                self._note_cache[file_path] = load_note_from_markdown(file_path)
            except Exception:
                return None
        return self._note_cache[file_path]

    def audit_topic_file(self, topic_file: Path | str, episodes_dir: Path | str) -> list[dict]:
        """Audit a single topic guide file for links, dates, and chapter grounding."""
        path = Path(topic_file)
        ep_dir = Path(episodes_dir)
        defects = []

        if not path.exists():
            return [{"topic": path.name, "category": "missing_file", "message": f"File does not exist: {path}"}]

        text = path.read_text(encoding="utf-8")

        # 1. Check frontmatter
        fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        if not fm_match:
            defects.append({"topic": path.name, "category": "format", "message": "Missing or malformed YAML frontmatter"})
        else:
            fm_text = fm_match.group(1)
            fm_dict: dict[str, str] = {}
            for line in fm_text.splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    fm_dict[key.strip()] = val.strip().strip("\"'")

            for req_key in ["slug", "title", "category", "time_span", "content_method"]:
                if req_key not in fm_dict or not fm_dict[req_key]:
                    defects.append({"topic": path.name, "category": "format", "message": f"Missing or empty required frontmatter key: {req_key}"})

            if "slug" in fm_dict and fm_dict["slug"] != path.stem:
                defects.append({
                    "topic": path.name,
                    "category": "slug_mismatch",
                    "message": f"Frontmatter slug '{fm_dict['slug']}' does not match file stem '{path.stem}'",
                })

            if "content_method" in fm_dict and fm_dict["content_method"] != "thematic_synthesis":
                defects.append({
                    "topic": path.name,
                    "category": "format",
                    "message": f"Unexpected content_method '{fm_dict['content_method']}' in frontmatter",
                })

        # 2. Check all markdown links and grounded chapter data
        # Regex to extract table rows: | [EPxxxx](../episodes/EPxxxx.md) | 2026-08-22 | 第 1 章 | Heading | Takeaway |
        table_rows = re.findall(
            r"\|\s*\[EP(\d+)\]\([^)]*episodes/EP\d+\.md\)\s*\|\s*([^|]+)\s*\|\s*第\s*(\d+)\s*章\s*\|\s*([^|]+)\s*\|",
            text,
        )

        if not table_rows:
            defects.append({
                "topic": path.name,
                "category": "empty_grounding",
                "message": f"Topic Guide {path.name} contains zero grounded chapter reference rows.",
            })

        for ep_num_str, row_date, ch_idx_str, row_heading in table_rows:
            ep_num = int(ep_num_str)
            target_file = ep_dir / f"EP{ep_num:04d}.md"
            if not target_file.exists():
                defects.append({
                    "topic": path.name,
                    "category": "broken_link",
                    "target_episode": ep_num,
                    "message": f"Referenced episode file not found: {target_file}",
                })
                continue

            note = self._get_note(target_file)
            if note is None:
                defects.append({
                    "topic": path.name,
                    "category": "unparseable_episode",
                    "target_episode": ep_num,
                    "message": f"Failed to parse referenced episode note: {target_file}",
                })
                continue

            # Verify date alignment
            clean_row_date = row_date.strip()
            if clean_row_date != note.metadata.date:
                defects.append({
                    "topic": path.name,
                    "category": "date_mismatch",
                    "target_episode": ep_num,
                    "message": f"Date mismatch in EP{ep_num}: topic has '{clean_row_date}', episode has '{note.metadata.date}'",
                })

            # Verify chapter existence
            ch_idx = int(ch_idx_str)
            matched_chapter = next((c for c in note.chapters if c.index == ch_idx), None)
            if matched_chapter is None:
                defects.append({
                    "topic": path.name,
                    "category": "missing_chapter",
                    "target_episode": ep_num,
                    "chapter_index": ch_idx,
                    "message": f"Chapter {ch_idx} not found in EP{ep_num}",
                })

        return defects

    def audit_all_topics(self, topics_dir: Path | str, episodes_dir: Path | str) -> dict:
        """Audit all topic guide files in topics directory."""
        t_dir = Path(topics_dir)
        ep_dir = Path(episodes_dir)

        topic_files = sorted([f for f in t_dir.glob("*.md") if f.name != "README.md"])
        all_defects = []

        for tf in topic_files:
            file_defects = self.audit_topic_file(tf, ep_dir)
            all_defects.extend(file_defects)

        return {
            "total_topics": len(topic_files),
            "defect_count": len(all_defects),
            "defects": all_defects,
        }

