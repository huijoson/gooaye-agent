#!/usr/bin/env python3
"""Unit tests for transcript sanitization, segmentation, and feature extraction."""

from __future__ import annotations

import unittest
from transcript_processor import (
    TranscriptSanitizer,
    TranscriptSegmenter,
    TranscriptFeatureExtractor,
)


class TestTranscriptProcessor(unittest.TestCase):
    def setUp(self) -> None:
        self.sanitizer = TranscriptSanitizer()
        self.segmenter = TranscriptSegmenter(sanitizer=self.sanitizer)
        self.features = TranscriptFeatureExtractor()

    def test_sponsor_removal_separator(self) -> None:
        text = """
本集節目由銀座白石贊助播出。專屬優惠碼領取。
***
唸完前面這個廣告詞，好我們今天來聊聊最近的市場情況。
聯準會降息預期持續發酵。
"""
        cleaned = self.sanitizer.clean(text)
        self.assertNotIn("銀座白石", cleaned)
        self.assertNotIn("專屬優惠碼", cleaned)
        self.assertIn("聯準會降息預期持續發酵", cleaned)

    def test_clean_excerpt(self) -> None:
        raw = "我覺得那時候看到行情走跌，其實心裡非常糾結。"
        cleaned = self.sanitizer.clean_excerpt(raw)
        self.assertEqual(cleaned, "那時候看到行情走跌，其實心裡非常糾結。")
        self.assertTrue(cleaned.endswith("。"))

    def test_clean_excerpt_truncation(self) -> None:
        long_sentence = "這是一段非常長的摘錄句，" * 20
        truncated = self.sanitizer.clean_excerpt(long_sentence, max_chars=50)
        self.assertTrue(len(truncated) <= 50)
        self.assertTrue(truncated.endswith("…"))

    def test_split_seeds(self) -> None:
        summary = "本集探討歐洲疫情擴散引發全球消費緊縮；分析外資在台股匯率與期貨佈局動向；最後提醒投資人注意技術面空頭排列特徵。"
        seeds = self.segmenter.split_seeds(summary)
        self.assertTrue(3 <= len(seeds) <= 6)
        self.assertIn("歐洲疫情", seeds[0])

    def test_sentence_segmentation(self) -> None:
        text = "這是第一句。這是第二句！這是第三句嗎？這是最後一句。"
        sentences = self.segmenter.segment_sentences(text)
        self.assertEqual(len(sentences), 4)

    def test_features_and_similarity(self) -> None:
        f1 = self.features.features("台積電 3nm 製程產能滿載")
        f2 = self.features.features("台積電先進製程產能滿載動能強勁")
        f3 = self.features.features("生鮮超市特價優惠促銷")

        sim_related = self.features.similarity(f1, f2)
        sim_unrelated = self.features.similarity(f1, f3)

        self.assertTrue(sim_related > 0.3)
        self.assertTrue(sim_unrelated < 0.1)


if __name__ == "__main__":
    unittest.main()
