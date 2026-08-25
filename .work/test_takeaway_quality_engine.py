#!/usr/bin/env python3
"""Unit tests for TakeawayQualityEngine and TakeawayResolvers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from domain import EpisodeMetadata, ChapterEvidence
from takeaway_quality_engine import TakeawayQualityEngine, TakeawayDefectCategory
from takeaway_resolver import (
    CachedTakeawayResolver,
    DeterministicTakeawayResolver,
    CompositeTakeawayResolver,
)


class TestTakeawayQualityEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = TakeawayQualityEngine()
        self.sample_excerpts = (
            "歐洲疫情擴散導致全球消費緊縮與恐慌性拋售，投資人切忌過度槓桿與盲目接飛刀。",
            "在空頭排列確立的格局下，拉高現金水位並嚴格設定停損點才能有效保全資本。",
        )

    def test_evaluate_valid_takeaway(self) -> None:
        valid = "歐洲疫情擴散引發市場恐慌拋售，投資人應嚴格控制槓桿並提高現金水位以保全資本。"
        self.assertTrue(self.engine.evaluate(valid, self.sample_excerpts))
        report = self.engine.diagnose(valid, self.sample_excerpts)
        self.assertTrue(report.is_valid)
        self.assertEqual(report.feedback_message, "合格")

    def test_detect_meta_filler(self) -> None:
        meta_takeaway = "主委在本段主要分享了歐洲疫情的發展，並提醒大家要做好部位管理。"
        report = self.engine.diagnose(meta_takeaway, self.sample_excerpts)
        self.assertFalse(report.is_valid)
        categories = [d.category for d in report.defects]
        self.assertIn(TakeawayDefectCategory.META_FILLER, categories)

    def test_detect_length_defects(self) -> None:
        short_takeaway = "疫情很嚴重。"
        report_short = self.engine.diagnose(short_takeaway, self.sample_excerpts)
        self.assertFalse(report_short.is_valid)
        self.assertIn(TakeawayDefectCategory.LENGTH, [d.category for d in report_short.defects])

        long_takeaway = "這是一段非常冗長的核心觀點敘述，" * 10
        report_long = self.engine.diagnose(long_takeaway, self.sample_excerpts)
        self.assertFalse(report_long.is_valid)
        self.assertIn(TakeawayDefectCategory.LENGTH, [d.category for d in report_long.defects])

    def test_detect_weak_grounding(self) -> None:
        unrelated = "美股科技七巨頭財報表現亮眼帶動那斯達克指數持續創下歷史新高紀錄。"
        report = self.engine.diagnose(unrelated, self.sample_excerpts)
        self.assertFalse(report.is_valid)
        self.assertIn(TakeawayDefectCategory.WEAK_GROUNDING, [d.category for d in report.defects])

    def test_deterministic_takeaway_extraction(self) -> None:
        excerpts = (
            "台積電 CoWoS 先進封裝產能持續供不應求，帶動相關設備與材料廠營收表現亮眼。",
            "但投資人應留意短期股價漲幅過大與本益比偏高的估值修正風險。",
        )
        takeaway = self.engine.extract_deterministic_takeaway(excerpts)
        self.assertTrue(20 <= len(takeaway) <= 65)
        self.assertTrue(self.engine.evaluate(takeaway, excerpts))

    def test_repair_meta_filler(self) -> None:
        flawed = "主委在本段強調歐洲疫情擴散導致全球消費緊縮與恐慌性拋售，投資人切忌過度槓桿與盲目接飛刀。"
        repaired = self.engine.repair(flawed, self.sample_excerpts)
        self.assertTrue(self.engine.evaluate(repaired, self.sample_excerpts))
        self.assertNotIn("主委在本段", repaired)


class TestTakeawayResolvers(unittest.TestCase):
    def setUp(self) -> None:
        self.meta = EpisodeMetadata(
            number=1,
            youtube_id="vid1",
            youtube_url="https://youtube.com/watch?v=vid1",
            youtube_title="EP1 測試",
            display_title="EP1 策展標題",
            date="2020-02-27",
            date_source="transcript_archive",
            duration_str="20:00",
            duration_seconds=1200,
            archive_url="https://example.com",
            summary="測試摘要",
        )
        self.raw_chapters = [
            ChapterEvidence(
                index=1,
                seed_title="總經環境與疫情衝擊",
                excerpts=(
                    "歐洲疫情擴散導致全球消費緊縮與恐慌性拋售，投資人切忌過度槓桿與盲目接飛刀。",
                    "在空頭排列確立的格局下，拉高現金水位並嚴格設定停損點才能有效保全資本。",
                ),
                position=10,
            )
        ]

    def test_deterministic_resolver(self) -> None:
        resolver = DeterministicTakeawayResolver()
        takeaways = resolver.resolve(self.meta, self.raw_chapters)
        self.assertEqual(len(takeaways), 1)
        self.assertTrue(20 <= len(takeaways[0]) <= 65)
        self.assertTrue("疫情" in takeaways[0] or "現金" in takeaways[0] or "空頭" in takeaways[0])

    def test_cached_resolver(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            cache_file = cache_dir / "EP0001.json"
            valid_takeaway = "歐洲疫情擴散導致全球消費緊縮，投資人應拉高現金水位以防禦空頭修正風險。"
            cache_file.write_text(
                json.dumps({
                    "episode": 1,
                    "takeaways": [valid_takeaway],
                }, ensure_ascii=False),
                encoding="utf-8",
            )

            resolver = CachedTakeawayResolver(cache_dir=cache_dir)
            resolved = resolver.resolve(self.meta, self.raw_chapters)
            self.assertEqual(resolved, [valid_takeaway])

    def test_composite_resolver_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            cached = CachedTakeawayResolver(cache_dir=cache_dir)
            deterministic = DeterministicTakeawayResolver()
            composite = CompositeTakeawayResolver(primary=cached, secondary=deterministic)

            resolved = composite.resolve(self.meta, self.raw_chapters)
            self.assertEqual(len(resolved), 1)
            self.assertTrue(len(resolved[0]) >= 20)


if __name__ == "__main__":
    unittest.main()
