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

    def test_detect_qa_boundary(self) -> None:
        text_with_qa = (
            "前面是長篇的市場與總經討論分析。" * 30
            + "好那接著進入 QA 的部分。第一位朋友留言問道關於美股槓桿 ETF 的配置。"
            + "第二位朋友詢問關於台積電與先進封裝供應鏈的看法。" * 10
        )
        pos = self.segmenter.detect_qa_boundary(text_with_qa)
        self.assertGreater(pos, 0)
        self.assertIn("QA", text_with_qa[pos : pos + 30])

        text_no_qa = "整集節目都在深度討論半導體設備與先進封裝產業景氣循環，完全沒有問答環節。" * 40
        self.assertEqual(self.segmenter.detect_qa_boundary(text_no_qa), -1)

    def test_segment_semantic_chapters(self) -> None:
        text = (
            "本集節目由廣告贊助。***"
            + "我們首先來看全球總體經濟與聯準會利率決策會議的最新動向。" * 20
            + "接著轉向半導體產業鏈與晶圓代工產能利用率分析。" * 20
            + "再來討論記憶體市場庫存去化進度與報價反彈趨勢。" * 20
            + "好那接下來進入 QA 的部分。第一位聽眾問海外券商開戶與匯款注意事項。" * 15
            + "下一位聽眾問長期投資指數型 ETF 該如何設定再平衡週期。" * 15
        )
        windows = self.segmenter.segment_semantic_chapters(text, target_count=5)
        self.assertGreaterEqual(len(windows), 4)
        self.assertTrue(any(w.is_qa for w in windows))
        self.assertTrue(any(not w.is_qa for w in windows))
        for idx, w in enumerate(windows, 1):
            self.assertEqual(w.index, idx)
            self.assertTrue(len(w.sentences) > 0)
            self.assertTrue(len(w.text) > 0)
            self.assertGreaterEqual(w.position, 0)


if __name__ == "__main__":
    unittest.main()
