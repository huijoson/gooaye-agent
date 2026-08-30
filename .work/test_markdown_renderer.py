#!/usr/bin/env python3
"""Unit tests for MarkdownRenderer."""

from __future__ import annotations

import unittest
from collections import Counter
from domain import EpisodeMetadata, Chapter, EpisodeNote, SynthesisSummary, TopicDefinition
from markdown_renderer import MarkdownRenderer


class TestMarkdownRenderer(unittest.TestCase):
    def test_index_renders_only_the_supplied_topic_catalog(self) -> None:
        topic = TopicDefinition(
            slug="only-topic",
            title="Only Topic",
            description="One explicit catalog entry.",
            category="test",
        )
        summary = SynthesisSummary(
            total_episodes=0,
            total_chapters=0,
            total_seconds=0,
            chapter_distribution=Counter(),
            notes=(),
        )

        rendered = MarkdownRenderer.render_index(
            (),
            summary,
            topics=(topic,),
        )

        self.assertIn("topics/only-topic.md", rendered)
        self.assertNotIn("topics/ai-hardware-and-semiconductor.md", rendered)

    def test_render_episode_and_index(self) -> None:
        meta1 = EpisodeMetadata(
            number=1,
            youtube_id="id1",
            youtube_url="https://youtube.com/watch?v=id1",
            youtube_title="EP1 標題",
            display_title="EP1 策展標題",
            date="2020-02-27",
            date_source="transcript_archive",
            duration_str="20:00",
            duration_seconds=1200,
            archive_url="https://whatmkreallysaid.com/1",
            summary="摘要1",
        )
        ch1 = Chapter(
            index=1,
            heading="章節標題一",
            takeaway="台股受國際情勢影響震盪，投資人宜以現貨與長期視角應對。",
            excerpts=("摘錄1", "摘錄2", "摘錄3", "摘錄4"),
            position=10,
        )
        note1 = EpisodeNote(metadata=meta1, chapters=(ch1,))

        rendered_slim = MarkdownRenderer.render_episode(note1, mode="slim")
        self.assertIn("EP1｜EP1 策展標題", rendered_slim)
        self.assertIn("- **核心觀點：** 台股受國際情勢影響震盪，投資人宜以現貨與長期視角應對。", rendered_slim)
        self.assertIn("- 摘錄1", rendered_slim)
        self.assertIn("- 摘錄2", rendered_slim)
        self.assertNotIn("- 摘錄3", rendered_slim)

        rendered_full = MarkdownRenderer.render_episode(note1, mode="full")
        self.assertIn("EP1｜EP1 策展標題", rendered_full)
        self.assertIn("- **核心觀點：** 台股受國際情勢影響震盪，投資人宜以現貨與長期視角應對。", rendered_full)
        self.assertIn("- 摘錄1", rendered_full)
        self.assertIn("- 摘錄2", rendered_full)
        self.assertIn("- 摘錄3", rendered_full)
        self.assertIn("- 摘錄4", rendered_full)

        summary = SynthesisSummary(
            total_episodes=1,
            total_chapters=1,
            total_seconds=1200,
            chapter_distribution=Counter({1: 1}),
            notes=(note1,),
        )

        readme = MarkdownRenderer.render_readme([note1], summary)
        self.assertIn("Gooaye 股癌 YouTube 全集章節觀念整理", readme)
        self.assertIn("收錄 **1 支目前公開的 YouTube 影片**", readme)

        index = MarkdownRenderer.render_index([note1], summary)
        self.assertIn("# 全集索引", index)
        self.assertIn("[EP1](episodes/EP0001.md)", index)

    def test_readme_and_index_derive_range_and_chapter_range_from_notes(self) -> None:
        notes = []
        for number, chapter_count in ((7, 2), (12, 4)):
            metadata = EpisodeMetadata(
                number=number,
                youtube_id=f"id{number}",
                youtube_url=f"https://youtube.com/watch?v=id{number}",
                youtube_title=f"EP{number} 標題",
                display_title=f"EP{number} 策展標題",
                date="2026-01-01",
                date_source="fixture",
                duration_str="1:00",
                duration_seconds=60,
                archive_url="https://example.test",
                summary="摘要",
            )
            chapters = tuple(
                Chapter(index=index, heading=f"章節 {index}", excerpts=("可驗證的逐字稿證據。",))
                for index in range(1, chapter_count + 1)
            )
            notes.append(EpisodeNote(metadata=metadata, chapters=chapters))
        summary = SynthesisSummary(
            total_episodes=2,
            total_chapters=6,
            total_seconds=120,
            chapter_distribution=Counter({2: 1, 4: 1}),
            notes=tuple(notes),
        )

        readme = MarkdownRenderer.render_readme(notes, summary)
        index = MarkdownRenderer.render_index(notes, summary)

        self.assertIn("涵蓋 EP7–EP12", readme)
        self.assertIn("每份 `episodes/EPxxxx.md` 包含 YAML metadata、YouTube 原始資訊、2–4 個觀念章節", readme)
        self.assertIn("涵蓋 EP7–EP12", index)


if __name__ == "__main__":
    unittest.main()
