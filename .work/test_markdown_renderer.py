#!/usr/bin/env python3
"""Unit tests for MarkdownRenderer."""

from __future__ import annotations

import unittest
from collections import Counter
from domain import EpisodeMetadata, Chapter, EpisodeNote, SynthesisSummary
from markdown_renderer import MarkdownRenderer


class TestMarkdownRenderer(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
