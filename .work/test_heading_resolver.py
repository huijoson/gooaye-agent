#!/usr/bin/env python3
"""Unit tests for HeadingResolvers (Cached, Deterministic, Composite, Ollama)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from domain import EpisodeMetadata, ChapterEvidence
from heading_quality_engine import HeadingQualityEngine
from heading_resolver import (
    CachedHeadingResolver,
    DeterministicHeadingResolver,
    CompositeHeadingResolver,
)


class TestHeadingResolvers(unittest.TestCase):
    def setUp(self) -> None:
        self.quality = HeadingQualityEngine()
        self.meta = EpisodeMetadata(
            number=1,
            youtube_id="vid1",
            youtube_url="https://youtube.com/watch?v=vid1",
            youtube_title="EP1",
            display_title="歐洲疫情與股市崩跌",
            date="2020-02-27",
            date_source="transcript_archive",
            duration_str="23:43",
            duration_seconds=1423,
            archive_url="https://whatmkreallysaid.com/ep1",
            summary="歐洲疫情與股市崩跌分析。",
        )
        self.evidence = [
            ChapterEvidence(
                index=1,
                seed_title="歐洲疫情",
                excerpts=(
                    "去看醫生前其實是非常糾結的，因為現在在歐洲呢，其實排斥亞洲人的這個氣氛是蠻濃厚的。",
                    "當然就是目前在歐洲的氛圍，就是看到亞洲人會閃。",
                ),
                position=100,
            ),
            ChapterEvidence(
                index=2,
                seed_title="股市空頭排列",
                excerpts=(
                    "最簡單的做法呢，就是看你的股市是不是走入空頭排列。",
                    "也就是說你的，譬如說週均線、月均線、季均線的排列是不是已經完全地進入空頭了。",
                ),
                position=500,
            ),
        ]

    def test_deterministic_resolver(self) -> None:
        resolver = DeterministicHeadingResolver(quality_engine=self.quality)
        headings = resolver.resolve(self.meta, self.evidence)
        self.assertEqual(len(headings), 2)
        for h, ev in zip(headings, self.evidence):
            self.assertTrue(self.quality.evaluate(h, ev.excerpts, self.meta.summary))

    def test_cached_resolver_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            cache_file = cache_dir / "EP0001.json"
            cache_file.write_text(
                json.dumps({
                    "episode": 1,
                    "headings": ["歐洲排斥亞洲人氛圍濃厚", "股市走入空頭排列特徵"],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            resolver = CachedHeadingResolver(cache_dir=cache_dir, quality_engine=self.quality)
            headings = resolver.resolve(self.meta, self.evidence)
            self.assertIsNotNone(headings)
            self.assertEqual(headings, ["歐洲排斥亞洲人氛圍濃厚", "股市走入空頭排列特徵"])

    def test_cached_resolver_invalid_falls_back_in_composite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            cache_file = cache_dir / "EP0001.json"
            # Invalid heading (too short and bad prefix)
            cache_file.write_text(
                json.dumps({
                    "episode": 1,
                    "headings": ["另外", "短"],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            cached_resolver = CachedHeadingResolver(cache_dir=cache_dir, quality_engine=self.quality)
            self.assertIsNone(cached_resolver.resolve(self.meta, self.evidence))

            composite = CompositeHeadingResolver(cache_dir=cache_dir, quality_engine=self.quality)
            headings = composite.resolve(self.meta, self.evidence)
            self.assertEqual(len(headings), 2)
            for h, ev in zip(headings, self.evidence):
                self.assertTrue(self.quality.evaluate(h, ev.excerpts, self.meta.summary))


if __name__ == "__main__":
    unittest.main()
