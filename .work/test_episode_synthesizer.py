#!/usr/bin/env python3
"""Unit test suite for EpisodeNoteSynthesizer - Testing in-memory pipeline, evidence extraction, heading resolvers, and markdown emission."""

from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from episode_synthesizer import (
    EpisodeNoteSynthesizer,
    EpisodeMetadata,
    CachedHeadingResolver,
    DeterministicHeadingResolver,
    CompositeHeadingResolver,
)
from heading_quality_engine import HeadingQualityEngine
from episode_source_repository import EpisodeSourceRepository
from domain import EpisodeSourceSnapshot


class TestEpisodeNoteSynthesizer(unittest.TestCase):
    def setUp(self) -> None:
        self.quality = HeadingQualityEngine()
        self.synthesizer = EpisodeNoteSynthesizer(quality_engine=self.quality)

    def test_clean_transcript_sponsor_removal(self) -> None:
        raw_text = """
本集節目由銀座白石贊助播出。日本頂級婚戒品牌，全台門市週年慶優惠中，歡迎至資訊欄連結領取折扣碼。
***
唸完前面這個廣告詞，好我們今天來聊聊最近的市場情況。
這週美股大盤波動非常劇烈，主要受到通膨數據高於預期的影響。
投資人應該注意手中持股的風險控管，不要過度槓桿操作。
"""
        cleaned = self.synthesizer.clean_transcript(raw_text)
        self.assertNotIn("銀座白石", cleaned)
        self.assertNotIn("折扣碼", cleaned)
        self.assertIn("這週美股大盤波動非常劇烈", cleaned)
        self.assertIn("通膨數據", cleaned)

    def test_split_seeds(self) -> None:
        summary = "本集探討歐洲疫情擴散引發全球消費緊縮；分析外資在台股匯率與期貨佈局動向；最後提醒投資人注意技術面空頭排列特徵。"
        seeds = self.synthesizer.split_seeds(summary)
        self.assertTrue(3 <= len(seeds) <= 6)
        self.assertIn("歐洲疫情", seeds[0])

    def test_source_repository_merges_real_legacy_and_normalized_sources(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            channel_path = root / "channel.json"
            archive_path = root / "episodes.json"
            transcript_dir = root / "full-transcripts"
            transcript_dir.mkdir()
            channel_path.write_text(
                json.dumps({"entries": [{"id": "xLS-2whm8Aw", "title": "EP1 | 舊集", "duration": 60}]}),
                encoding="utf-8",
            )
            archive_path.write_text(
                json.dumps([{"number": 1, "filename": "EP1.md", "title": "舊集", "date": "2020-02-27", "summary": "舊集摘要"}]),
                encoding="utf-8",
            )
            (transcript_dir / "EP0001.md").write_text("# EP1\n\n舊逐字稿", encoding="utf-8")
            repository = EpisodeSourceRepository(
                snapshot_root=root / "episode-sources",
                legacy_channel_path=channel_path,
                legacy_archive_path=archive_path,
                legacy_transcript_dir=transcript_dir,
            )
            repository.commit(
                EpisodeSourceSnapshot(
                    number=691,
                    youtube_id="J-e9oxqLzpc",
                    youtube_title="EP691 | birthday",
                    published_at="2026-08-26T08:23:12+00:00",
                    duration_seconds=2995,
                    archive_filename="EP691.md",
                    display_title="新集",
                    archive_date="2026-08-26",
                    summary="新集摘要",
                    transcript="# EP691 新集\n\n" + "完整逐字稿" * 200,
                    source_urls={"youtube_metadata": "https://example.test/youtube", "duration_metadata": "https://example.test/soundon", "archive_index": "https://example.test/index", "transcript": "https://example.test/transcript"},
                    fetched_at="2026-08-28T00:00:00+00:00",
                )
            )

            synthesizer = EpisodeNoteSynthesizer(source_repository=repository)

            self.assertEqual(synthesizer.episode_numbers, [1, 691])
            self.assertEqual(synthesizer.get_metadata(691).youtube_id, "J-e9oxqLzpc")
            self.assertTrue(synthesizer.load_transcript(691).startswith("# EP691"))
            self.assertTrue(synthesizer.load_transcript(1).startswith("# EP1"))

    def test_deterministic_heading_resolver(self) -> None:
        meta = EpisodeMetadata(
            number=1,
            youtube_id="xLS-2whm8Aw",
            youtube_url="https://www.youtube.com/watch?v=xLS-2whm8Aw",
            youtube_title="EP1 | 武漢肺炎 股市崩盤",
            display_title="歐洲疫情、股市崩跌與投資策略",
            date="2020-02-27",
            date_source="transcript_archive",
            duration_str="23:43",
            duration_seconds=1423,
            archive_url="https://whatmkreallysaid.com/",
            summary="歐洲疫情與股市崩跌分析。",
        )
        raw_chapters = [
            {
                "title": "歐洲疫情",
                "excerpts": (
                    "去看醫生前其實是非常糾結的，因為現在在歐洲呢，其實排斥亞洲人的這個氣氛是蠻濃厚的。",
                    "當然就是目前在歐洲的氛圍，就是看到亞洲人會閃。",
                ),
                "position": 100,
            },
            {
                "title": "股市空頭排列",
                "excerpts": (
                    "最簡單的做法呢，就是看你的股市是不是走入空頭排列。",
                    "也就是說你的，譬如說週均線、月均線、季均線的排列是不是已經完全地進入空頭了。",
                ),
                "position": 500,
            },
        ]
        resolver = DeterministicHeadingResolver(quality_engine=self.quality)
        headings = resolver.resolve(meta, raw_chapters)
        self.assertEqual(len(headings), 2)
        for h in headings:
            self.assertTrue(len(h) >= 8)
            self.assertTrue(self.quality.evaluate(h, raw_chapters[0]["excerpts"] if h == headings[0] else raw_chapters[1]["excerpts"], meta.summary))

    def test_composite_resolver_fallback(self) -> None:
        meta = EpisodeMetadata(
            number=99999,  # Non-existent episode number
            youtube_id="dummy",
            youtube_url="https://www.youtube.com/watch?v=dummy",
            youtube_title="EP99999",
            display_title="測試單集",
            date="2026-01-01",
            date_source="test",
            duration_str="10:00",
            duration_seconds=600,
            archive_url="https://whatmkreallysaid.com/",
            summary="測試摘要說明。",
        )
        raw_chapters = [
            {
                "title": "晶圓代工成熟製程",
                "excerpts": (
                    "成熟製程晶圓代工廠稼動率近期出現回溫跡象，客戶庫存去化接近尾聲。",
                    "各大車用晶片與工控晶片供應商開始啟動小規模急單投片。",
                ),
                "position": 50,
            }
        ]
        # Composite should fallback to deterministic without raising error
        composite = CompositeHeadingResolver(quality_engine=self.quality)
        headings = composite.resolve(meta, raw_chapters)
        self.assertEqual(len(headings), 1)
        self.assertTrue(len(headings[0]) >= 8)

    def test_synthesize_single_episode_end_to_end(self) -> None:
        if 1 not in self.synthesizer.episode_numbers:
            self.skipTest("EP1 data files not present in workspace")
        note = self.synthesizer.synthesize_episode(1)
        self.assertEqual(note.metadata.number, 1)
        self.assertTrue(len(note.chapters) >= 3)
        markdown_slim = note.render_markdown(mode="slim")
        markdown_full = note.render_markdown(mode="full")
        self.assertIn("episode: 1", markdown_slim)
        self.assertIn("## 章節觀念", markdown_slim)
        self.assertIn("## 資料來源與整理方式", markdown_slim)
        for ch in note.chapters:
            self.assertIn(f"### {ch.index}. {ch.heading}", markdown_slim)
            self.assertTrue(len(ch.takeaway) >= 15)
            self.assertIn(f"- **核心觀點：** {ch.takeaway}", markdown_slim)
            self.assertIn(f"- **核心觀點：** {ch.takeaway}", markdown_full)
            self.assertGreaterEqual(len(ch.excerpts), 2)

    def test_synthesize_notes_returns_complete_summary_without_writing(self) -> None:
        if not {1, 2}.issubset(self.synthesizer.episode_numbers):
            self.skipTest("EP1 and EP2 data files not present in workspace")
        with patch.object(Path, "write_text") as write_text:
            summary = self.synthesizer.synthesize_notes(
                max_workers=1,
                episode_numbers=(1, 2),
            )

            self.assertEqual([note.metadata.number for note in summary.notes], [1, 2])
            self.assertEqual(summary.total_episodes, 2)
            self.assertEqual(summary.total_chapters, sum(len(note.chapters) for note in summary.notes))
            write_text.assert_not_called()

    def test_synthesize_all_writes_dual_tier_files(self) -> None:
        import tempfile
        if 1 not in self.synthesizer.episode_numbers:
            self.skipTest("EP1 data files not present in workspace")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            summary = self.synthesizer.synthesize_all(
                output_dir=out_dir,
                episode_numbers=[1],
            )
            self.assertEqual(summary.total_episodes, 1)
            ep_file = out_dir / "episodes/EP0001.md"
            full_file = out_dir / "episodes/EP0001.full.md"
            index_file = out_dir / "_index.md"
            readme_file = out_dir / "README.md"
            self.assertTrue(ep_file.exists())
            self.assertTrue(full_file.exists())
            self.assertTrue(index_file.exists())
            self.assertTrue(readme_file.exists())

            ep_content = ep_file.read_text(encoding="utf-8")
            full_content = full_file.read_text(encoding="utf-8")
            self.assertIn("content_method: \"hybrid_extractive_distilled\"", ep_content)
            self.assertIn("content_method: \"hybrid_extractive_distilled\"", full_content)
            self.assertIn("**核心觀點：**", ep_content)
            self.assertIn("**核心觀點：**", full_content)


if __name__ == "__main__":
    unittest.main()
