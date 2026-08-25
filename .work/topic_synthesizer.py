"""Thematic Topic Synthesizer and Renderer for Gooaye knowledge base."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Sequence

from domain import (
    EpisodeNote,
    ThematicChapterRef,
    ThematicMilestone,
    TopicDefinition,
    TopicGuide,
    yaml_string,
)


class TopicGuideSynthesizer:
    """Synthesizes structured topic guides across episode notes."""

    def __init__(self, score_threshold: float = 4.0):
        self.score_threshold = score_threshold

    def score_chapter(
        self,
        episode: EpisodeNote,
        chapter_index: int,
        heading: str,
        takeaway: str,
        excerpts: tuple[str, ...],
        keywords: tuple[str, ...],
    ) -> tuple[float, tuple[str, ...]]:
        """Score chapter relevance against topic keywords."""
        score = 0.0
        matched = set()

        heading_lower = heading.lower()
        takeaway_lower = takeaway.lower()
        excerpts_lower = " ".join(excerpts).lower()

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
                    episode=ep,
                    chapter_index=ch.index,
                    heading=ch.heading,
                    takeaway=ch.takeaway,
                    excerpts=ch.excerpts,
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
            "- [🔗 相關集數索引與引用列表](#-相關集數索引與引用列表)",
            "",
            "---",
            "",
            "## 🎯 核心結論速覽",
            "",
        ]

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
                ep_str = f"EP{ref.episode_number:04d}"
                ep_link = f"[{ref.episode_number:04d}｜{ref.episode_title}](../episodes/{ep_str}.md)"
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
