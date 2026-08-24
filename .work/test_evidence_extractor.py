#!/usr/bin/env python3
"""Unit tests for EvidenceExtractor."""

from __future__ import annotations

import unittest
from domain import ChapterEvidence
from evidence_extractor import EvidenceExtractor


class TestEvidenceExtractor(unittest.TestCase):
    def setUp(self) -> None:
        self.extractor = EvidenceExtractor()

    def test_extract_evidence_basic(self) -> None:
        summary = "探討歐洲疫情蔓延情況與排斥氛圍；分析全球股市空頭排列與均線特徵；最後說明投資人部位控管與風險管理策略。"
        transcript = """
本集節目由測試贊助播出。優惠碼折扣。
***
我們今天來聊聊最近歐洲疫情的狀況。去看醫生前其實是非常糾結的，因為現在在歐洲呢，其實排斥亞洲人的這個氣氛是蠻濃厚的。
當然就是目前在歐洲的氛圍，就是看到亞洲人會閃，大家彼此都非常提防。
接著來看股市方面。最簡單的做法呢，就是看你的股市是不是走入空頭排列，不要逆勢硬接飛刀。
也就是說你的週線月線季均線排列是不是已經完全地進入空頭了，如果是的話就要特別小心。
在這種行情劇烈波動之下，投資人一定要做好部位控管與資金管理，不要過度槓桿操作。
把現金水位拉高並保留足夠的風險緩衝空間，才能在市場反轉時保護好自己的本金。
"""
        evidence = self.extractor.extract(summary, transcript)
        self.assertEqual(len(evidence), 3)
        for ev in evidence:
            self.assertIsInstance(ev, ChapterEvidence)
            self.assertEqual(len(ev.excerpts), 2)
            self.assertTrue(all(len(b) >= 10 for b in ev.excerpts))
            self.assertTrue(ev.position >= 0)

        # Check chronological ordering
        self.assertTrue(evidence[0].position <= evidence[1].position <= evidence[2].position)


if __name__ == "__main__":
    unittest.main()
