#!/usr/bin/env python3
"""Unit test suite for HeadingQualityEngine - Verifying all defect diagnostics and repairs."""

from __future__ import annotations

import unittest
from heading_quality_engine import HeadingQualityEngine, DefectCategory


class TestHeadingQualityEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = HeadingQualityEngine()

    def test_valid_heading(self) -> None:
        heading = "歐洲排斥亞洲人氛圍濃厚"
        excerpts = [
            "去看醫生前其實是非常糾結的，因為現在在歐洲呢，其實排斥亞洲人的這個氣氛是蠻濃厚的。",
            "當然就是目前在歐洲的氛圍，就是看到亞洲人會閃。",
        ]
        summary = "本集討論歐洲疫情蔓延情況、股市崩盤跡象以及個人操作心態。"
        report = self.engine.diagnose(heading, excerpts, summary)
        self.assertTrue(report.is_valid, f"Expected valid but got defects: {report.feedback_message}")
        self.assertTrue(self.engine.evaluate(heading, excerpts, summary))
        self.assertEqual(len(report.defects), 0)

    def test_format_length_defects(self) -> None:
        too_short = "短標題"
        report = self.engine.diagnose(too_short, ["測試摘錄一", "測試摘錄二"])
        self.assertFalse(report.is_valid)
        self.assertTrue(any(d.category == DefectCategory.FORMAT for d in report.defects))

        too_long = "這是一個非常非常非常非常非常非常非常長而且超過三十六個字上限限制的無效章節標題呀呀呀呀"
        report_long = self.engine.diagnose(too_long, ["測試摘錄一", "測試摘錄二"])
        self.assertFalse(report_long.is_valid)
        self.assertTrue(any(d.category == DefectCategory.FORMAT for d in report_long.defects))

    def test_unbalanced_syntax(self) -> None:
        unbalanced = "半導體產業鏈分析（台積電與聯電"
        excerpts = ["台積電營收亮眼分析", "聯電成熟製程展望"]
        report = self.engine.diagnose(unbalanced, excerpts)
        self.assertFalse(report.is_valid)
        self.assertTrue(any(d.category == DefectCategory.UNBALANCED_SYNTAX for d in report.defects))

    def test_ellipsis_forbidden(self) -> None:
        heading = "總體經濟與升息循環預期…"
        excerpts = ["總體經濟分析重點", "升息循環預期變化"]
        report = self.engine.diagnose(heading, excerpts)
        self.assertFalse(report.is_valid)
        self.assertTrue(any(d.category == DefectCategory.FORMAT and "ellipsis" in d.trigger for d in report.defects))

    def test_generic_terms(self) -> None:
        generic_cases = [
            "主題：台股市場觀察",
            "本段重點與實務建議",
            "聽眾問答時段分享",
            "Q&A 問題解答與雜談",
        ]
        excerpts = ["台股大盤指數波動", "解答聽眾投資策略提問"]
        for case in generic_cases:
            report = self.engine.diagnose(case, excerpts)
            self.assertFalse(report.is_valid, f"Expected {case} to be invalid")
            self.assertTrue(any(d.category == DefectCategory.GENERIC_TERMS for d in report.defects))

    def test_transition_prefixes(self) -> None:
        bad_prefixes = [
            "另外聊聊美股財報表現",
            "接著轉向航運股運價觀察",
            "比較各家伺服器代工廠",
            "的這個市場資金輪動狀況",
        ]
        excerpts = ["美股財報季各大科技巨頭獲利狀況", "航運股運價指數近期走勢"]
        for case in bad_prefixes:
            report = self.engine.diagnose(case, excerpts)
            self.assertFalse(report.is_valid, f"Expected {case} to have bad prefix defect")
            self.assertTrue(any(d.category == DefectCategory.TRANSITION_PREFIX for d in report.defects))

    def test_conversational_fragments(self) -> None:
        # Case from audit: EP6 ch1 with oral pronouns & temporal particle
        heading = "股癌聽眾誤用麥克風導致設備故障與他問我說是不是用錯邊的時候"
        excerpts = [
            "有聽眾寫信來問我說麥克風是不是用錯邊的時候，我才發現是真的用錯了。",
            "這個設備故障搞了很久，結果是我自己搞烏龍。",
        ]
        report = self.engine.diagnose(heading, excerpts)
        self.assertFalse(report.is_valid)
        self.assertTrue(any(d.category == DefectCategory.CONVERSATIONAL_FRAGMENT for d in report.defects))

        # Case with oral degree modifier: "滿抖"
        oral_heading = "清明連假大型集會活動節慶感染風險滿抖"
        oral_excerpts = [
            "那時候看到清明連假大家全部跑出去玩，其實心裡覺得滿抖的。",
            "境外移入個案持續增加，大型集會活動感染風險上升。",
        ]
        report_oral = self.engine.diagnose(oral_heading, oral_excerpts)
        self.assertFalse(report_oral.is_valid)
        self.assertTrue(any(d.category == DefectCategory.CONVERSATIONAL_FRAGMENT for d in report_oral.defects))

    def test_machine_glue(self) -> None:
        heading = "貼牌老師理所當然將盈虧自負刺臉與他們直接把妖魔鬼怪四個字刺在臉上"
        excerpts = [
            "那些貼牌老師理所當然將盈虧自負刺臉上，出事就推給學員。",
            "市場上這些人他們直接把妖魔鬼怪四個字刺在臉上，完全不避諱。",
        ]
        report = self.engine.diagnose(heading, excerpts)
        self.assertFalse(report.is_valid)
        self.assertTrue(any(d.category == DefectCategory.MACHINE_GLUE for d in report.defects))

    def test_summary_leakage(self) -> None:
        heading = "本集深入剖析總體經濟趨勢"
        excerpts = [
            "我們來看這週聯準會公佈的點陣圖變化。",
            "通膨數據比預期更為頑固，市場利率維持高檔。",
        ]
        summary = "本集深入剖析總體經濟趨勢，並解答聽眾各項資產配置難題。"
        report = self.engine.diagnose(heading, excerpts, summary)
        self.assertFalse(report.is_valid)
        self.assertTrue(any(d.category == DefectCategory.SUMMARY_LEAKAGE for d in report.defects))

    def test_broken_latin(self) -> None:
        heading = "穿戴裝置 Apple Watc 銷量分析"
        excerpts = [
            "今年 Apple Watch 銷量在智慧穿戴市場依然穩居第一名。",
            "各大供應鏈廠商營收表現持續受惠。",
        ]
        report = self.engine.diagnose(heading, excerpts)
        self.assertFalse(report.is_valid)
        self.assertTrue(any(d.category == DefectCategory.BROKEN_LATIN for d in report.defects))

    def test_deterministic_repair(self) -> None:
        awkward_heading = "這個東西滿抖的與說不出來送福利"
        excerpts = [
            "全球記憶體價格持續走跌，原廠庫存水位偏高，減產效果有限。",
            "伺服器需求成為支撐半導體晶圓代工廠稼動率的關鍵動能。",
        ]
        summary = "市場分析與記憶體產業概況說明。"
        repaired = self.engine.repair(awkward_heading, excerpts, summary)
        self.assertTrue(len(repaired) >= 8)
        self.assertTrue(self.engine.evaluate(repaired, excerpts, summary))
        report = self.engine.diagnose(repaired, excerpts, summary)
        self.assertTrue(report.is_valid, f"Repaired heading {repaired!r} must be valid but got defects: {report.feedback_message}")


if __name__ == "__main__":
    unittest.main()
