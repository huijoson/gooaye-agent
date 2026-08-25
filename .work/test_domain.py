#!/usr/bin/env python3
"""Unit tests for domain models and data structures."""

from __future__ import annotations

import unittest
from domain import (
    EpisodeMetadata,
    ChapterEvidence,
    Chapter,
    EpisodeNote,
    SynthesisSummary,
    DefectCategory,
    Defect,
    QualityReport,
    yaml_string,
    format_duration,
)


class TestDomainModels(unittest.TestCase):
    def test_yaml_string(self) -> None:
        self.assertEqual(yaml_string("Hello World"), '"Hello World"')
        self.assertEqual(yaml_string('Has "Quotes"'), '"Has \\"Quotes\\""')
        self.assertEqual(yaml_string("繁體中文標題"), '"繁體中文標題"')

    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(None), "未知")
        self.assertEqual(format_duration(45), "0:45")
        self.assertEqual(format_duration(1423), "23:43")
        self.assertEqual(format_duration(3665), "1:01:05")

    def test_chapter_evidence_serialization(self) -> None:
        ev = ChapterEvidence(
            index=1,
            seed_title="總經環境分析",
            excerpts=("摘錄一內容", "摘錄二內容", "摘錄三內容", "摘錄四內容"),
            position=150,
        )
        d = ev.to_dict()
        self.assertEqual(d["index"], 1)
        self.assertEqual(d["title"], "總經環境分析")
        self.assertEqual(d["excerpts"], ("摘錄一內容", "摘錄二內容", "摘錄三內容", "摘錄四內容"))
        self.assertEqual(d["position"], 150)

        restored = ChapterEvidence.from_dict(d)
        self.assertEqual(restored, ev)

    def test_episode_note_render_markdown_slim_and_full(self) -> None:
        meta = EpisodeMetadata(
            number=1,
            youtube_id="vid123",
            youtube_url="https://youtube.com/watch?v=vid123",
            youtube_title="EP1 | 測試標題",
            display_title="測試策展標題",
            date="2020-02-27",
            date_source="transcript_archive",
            duration_str="23:43",
            duration_seconds=1423,
            archive_url="https://whatmkreallysaid.com/ep1",
            summary="測試摘要",
        )
        ch1 = Chapter(
            index=1,
            heading="歐洲疫情與股市崩跌",
            takeaway="歐洲疫情擴散引發恐慌性拋售，投資人應嚴格控制槓桿並分批佈局。",
            excerpts=("摘錄A。", "摘錄B。", "摘錄C。", "摘錄D。"),
            position=10,
        )
        note = EpisodeNote(metadata=meta, chapters=(ch1,))
        
        # Test slim mode (default)
        md_slim = note.render_markdown(mode="slim")
        self.assertIn("episode: 1", md_slim)
        self.assertIn('content_method: "hybrid_extractive_distilled"', md_slim)
        self.assertIn("# EP1｜測試策展標題", md_slim)
        self.assertIn("### 1. 歐洲疫情與股市崩跌", md_slim)
        self.assertIn("- **核心觀點：** 歐洲疫情擴散引發恐慌性拋售，投資人應嚴格控制槓桿並分批佈局。", md_slim)
        self.assertIn("- 摘錄A。", md_slim)
        self.assertIn("- 摘錄B。", md_slim)
        self.assertNotIn("- 摘錄C。", md_slim)
        self.assertNotIn("- 摘錄D。", md_slim)

        # Test full mode
        md_full = note.render_markdown(mode="full")
        self.assertIn("episode: 1", md_full)
        self.assertIn('content_method: "hybrid_extractive_distilled"', md_full)
        self.assertIn("### 1. 歐洲疫情與股市崩跌", md_full)
        self.assertIn("- **核心觀點：** 歐洲疫情擴散引發恐慌性拋售，投資人應嚴格控制槓桿並分批佈局。", md_full)
        self.assertIn("- 摘錄A。", md_full)
        self.assertIn("- 摘錄B。", md_full)
        self.assertIn("- 摘錄C。", md_full)
        self.assertIn("- 摘錄D。", md_full)

    def test_quality_report(self) -> None:
        report_ok = QualityReport(heading="正常標題長度合格")
        self.assertTrue(report_ok.is_valid)
        self.assertEqual(report_ok.feedback_message, "合格")

        defect = Defect(category=DefectCategory.FORMAT, message="字數過短")
        report_defect = QualityReport(heading="短", defects=(defect,))
        self.assertFalse(report_defect.is_valid)
        self.assertEqual(report_defect.feedback_message, "字數過短")


if __name__ == "__main__":
    unittest.main()
