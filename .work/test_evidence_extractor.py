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

    def test_extract_evidence_autonomous_and_expanded(self) -> None:
        long_transcript = """
本集節目由 Sony 耳機贊助播出。輸入優惠碼享九折。
***
我們今天第一段先來聊聊美國聯準會最新公佈的利率決策與經濟褐皮書報告。
市場目前對於下半年的降息幅度有過度樂觀的預期，但從通膨黏滯性來看其實依然存在風險。
特別是在服務業通膨與工資增長方面，並未如市場預期般快速降溫。
因此投資人不應該過度押注單一方向的利率寬鬆政策，而應該保留足夠的風險緩衝空間。
接著來看半導體與 AI 伺服器供應鏈的最新拉貨動向與產能利用率。
台積電在 CoWoS 先進封裝產能的擴張速度超乎市場預期，帶動設備股與材料廠營收爆發。
包含散熱模組與水冷系統在 GB200 晶片上的滲透率正在快速拉升。
不過相關族群的本益比已經推升到歷史高檔區間，追價風險顯著增加。
再來討論記憶體產業的週期循環與 HBM 高頻寬記憶體的供需缺口。
原廠透過積極減產策略成功推升了 DRAM 與 NAND Flash 的合約報價。
但是消費性電子與智慧型手機的終端需求依然偏弱，復甦動能呈現高度結構性分化。
好那接著進入 QA 的部分。第一位聽眾問道初入市場的新手該如何建立核心持股與衛星配置。
主委建議新手應該先以大盤指數型 ETF 作為七成以上的核心底倉，維持穩健的長期報酬。
剩餘的三成資金再依個人風險承受度去挑選看好的產業龍頭或個別成長股。
下一位聽眾詢問在空頭市場或急速修正時應該如何執行停損與部位調整。
停損的本質是為了保護本金不受到毀滅性的傷害，絕對不能因為不甘心而盲目攤平。
"""
        evidence = self.extractor.extract(
            transcript=long_transcript,
            min_excerpts=2,
            max_excerpts=6,
        )
        self.assertGreaterEqual(len(evidence), 4)
        for ev in evidence:
            self.assertIsInstance(ev, ChapterEvidence)
            self.assertGreaterEqual(len(ev.excerpts), 2)
            self.assertLessEqual(len(ev.excerpts), 6)
            self.assertTrue(ev.seed_title != "")
            self.assertTrue(all(len(e) >= 10 for e in ev.excerpts))


if __name__ == "__main__":
    unittest.main()
