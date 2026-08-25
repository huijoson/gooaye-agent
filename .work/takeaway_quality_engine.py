"""Takeaway quality engine - Evaluates, diagnoses, and repairs chapter core takeaways (1-sentence summaries)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class TakeawayDefectCategory(str, Enum):
    """Categories of defects in chapter takeaways."""
    LENGTH = "length"
    META_FILLER = "meta_filler"
    WEAK_GROUNDING = "weak_grounding"
    GENERIC_OPINION = "generic_opinion"
    ORAL_FRAGMENT = "oral_fragment"
    UNBALANCED_SYNTAX = "unbalanced_syntax"


@dataclass(frozen=True)
class TakeawayDefect:
    """Represents a specific defect found in a takeaway."""
    category: TakeawayDefectCategory
    message: str
    trigger: str = ""


@dataclass(frozen=True)
class TakeawayReport:
    """Diagnostic report produced by TakeawayQualityEngine."""
    takeaway: str
    defects: tuple[TakeawayDefect, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        return len(self.defects) == 0

    @property
    def feedback_message(self) -> str:
        if self.is_valid:
            return "合格"
        return "；".join(d.message for d in self.defects)


class TakeawayQualityEngine:
    """Deep module for validating, diagnosing, and repairing 1-sentence takeaways."""

    MIN_LENGTH = 20
    MAX_LENGTH = 65

    META_PATTERNS = (
        re.compile(r"(?:主委|主持人|謝孟恭|孟恭|本段|本集|這段|這集|這章|本章|在這一節|在這段話)(?:在|於)?(?:主要)?(?:分享|提到|探討|分析|說明|聊到|點出|講到|表示|指出|認為|強調)", re.IGNORECASE),
        re.compile(r"(?:跟大家分享|跟大家聊聊|本篇主要在講|這段在講)", re.IGNORECASE),
    )

    ORAL_PATTERNS = (
        re.compile(r"^(?:我覺得|我認為|我想說|其實就是|就是說|等於說|老實說)[，,、\s]*", re.IGNORECASE),
        re.compile(r"(?:滿抖的|超香的|超爽的|真的是|搞不好|而已啦|之類的)", re.IGNORECASE),
    )

    GENERIC_PATTERNS = (
        re.compile(r"^(?:投資有賺有賠|股市有漲有跌|投資要小心|大家要做好準備|操作要理性|這件事非常重要|保持平常心)[。！？!?]?$"),
    )

    PAIRED_SYMBOLS = (
        ("（", "）"),
        ("(", ")"),
        ("《", "》"),
        ("「", "」"),
        ("『", "』"),
        ("【", "】"),
        ("[", "]"),
    )

    @staticmethod
    def compact(text: str) -> str:
        """Strip whitespace and punctuation for CJK comparison."""
        return "".join(re.findall(r"[\u3400-\u9fffa-zA-Z0-9]+", text)).lower()

    @staticmethod
    def bigrams(text: str) -> set[str]:
        val = TakeawayQualityEngine.compact(text)
        return {val[i : i + 2] for i in range(len(val) - 1)}

    def evaluate(self, takeaway: str, excerpts: Sequence[str]) -> bool:
        """Fast boolean evaluation of takeaway quality."""
        return self.diagnose(takeaway, excerpts).is_valid

    def diagnose(self, takeaway: str, excerpts: Sequence[str]) -> TakeawayReport:
        """Diagnose a candidate takeaway against all quality criteria."""
        takeaway = takeaway.strip()
        defects: list[TakeawayDefect] = []

        # 1. Length check
        if len(takeaway) < self.MIN_LENGTH:
            defects.append(
                TakeawayDefect(
                    category=TakeawayDefectCategory.LENGTH,
                    message=f"核心觀點長度過短（{len(takeaway)} 字，需至少 {self.MIN_LENGTH} 字）",
                    trigger=takeaway,
                )
            )
        elif len(takeaway) > self.MAX_LENGTH:
            defects.append(
                TakeawayDefect(
                    category=TakeawayDefectCategory.LENGTH,
                    message=f"核心觀點長度過長（{len(takeaway)} 字，最多 {self.MAX_LENGTH} 字）",
                    trigger=takeaway,
                )
            )

        # 2. Meta filler check
        for pat in self.META_PATTERNS:
            if m := pat.search(takeaway):
                defects.append(
                    TakeawayDefect(
                        category=TakeawayDefectCategory.META_FILLER,
                        message=f"包含禁止之元敘述或空話套話（'{m.group()}'）",
                        trigger=m.group(),
                    )
                )
                break

        # 3. Generic assertion check
        for pat in self.GENERIC_PATTERNS:
            if pat.search(takeaway):
                defects.append(
                    TakeawayDefect(
                        category=TakeawayDefectCategory.GENERIC_OPINION,
                        message="核心觀點為無實質判斷之泛稱廢話",
                        trigger=takeaway,
                    )
                )
                break

        # 4. Unbalanced syntax
        for open_sym, close_sym in self.PAIRED_SYMBOLS:
            if takeaway.count(open_sym) != takeaway.count(close_sym):
                defects.append(
                    TakeawayDefect(
                        category=TakeawayDefectCategory.UNBALANCED_SYNTAX,
                        message=f"括號或符號未成對（'{open_sym}' 與 '{close_sym}'）",
                        trigger=takeaway,
                    )
                )
                break

        # 5. Grounding check against verbatim excerpts
        if excerpts:
            takeaway_bigrams = self.bigrams(takeaway)
            excerpts_text = "".join(excerpts)
            excerpts_bigrams = self.bigrams(excerpts_text)
            if takeaway_bigrams:
                overlap = len(takeaway_bigrams & excerpts_bigrams) / len(takeaway_bigrams)
                if overlap < 0.30:
                    defects.append(
                        TakeawayDefect(
                            category=TakeawayDefectCategory.WEAK_GROUNDING,
                            message=f"核心觀點與逐字稿摘錄接地性不足（Bigram 覆蓋率僅 {overlap:.1%}）",
                            trigger=takeaway,
                        )
                    )

        return TakeawayReport(takeaway=takeaway, defects=tuple(defects))

    def _clean_takeaway_text(self, text: str) -> str:
        """Helper to sanitize and balance quotes/brackets in takeaway strings."""
        cleaned = text.strip().replace("「", "").replace("」", "").replace("『", "").replace("』", "")
        for pat in self.META_PATTERNS:
            cleaned = pat.sub("", cleaned)
        for pat in self.ORAL_PATTERNS:
            cleaned = pat.sub("", cleaned)
        cleaned = re.sub(r"^(?:所以|那|然後|其實|當然|反正|總之|以及|並且|首先就是在)[，,、\s]*", "", cleaned)
        cleaned = re.sub(r"[，,、\s]*(?:先這樣|大家掰掰|掰掰|掰)[。！？!?]*$", "。", cleaned)
        cleaned = re.sub(r"（[^）]*$", "", cleaned)  # Strip unclosed opening bracket at end
        cleaned = re.sub(r"\([^)]*$", "", cleaned)
        cleaned = re.sub(r"^[）)]+", "", cleaned)
        return cleaned.strip()

    def extract_deterministic_takeaway(self, excerpts: Sequence[str]) -> str:
        """Extract a grounded 1-sentence takeaway deterministically from excerpts."""
        if not excerpts:
            return "本段重點在於保持理性投資紀律與嚴格的風險管理措施。"

        cleaned_candidates: list[str] = []
        for e in excerpts:
            cleaned = self._clean_takeaway_text(e)
            if cleaned.strip("。") and not cleaned.endswith(("？", "?")):
                cleaned_candidates.append(cleaned.strip())

        for s in cleaned_candidates:
            if self.MIN_LENGTH <= len(s) <= self.MAX_LENGTH:
                terminal = s[-1] if s[-1] in "。！？!?" else "。"
                candidate = s.rstrip("。！？!?；;，,") + terminal
                if self.evaluate(candidate, excerpts):
                    return candidate

        # Try chaining candidates to reach MIN_LENGTH
        current = ""
        for s in cleaned_candidates:
            if not current:
                current = s.rstrip("。！？!?；;，,")
            else:
                current += "，" + s.rstrip("。！？!?；;，,").lstrip()
            if self.MIN_LENGTH <= len(current) <= self.MAX_LENGTH:
                candidate = current + "。"
                if self.evaluate(candidate, excerpts):
                    return candidate
            elif len(current) > self.MAX_LENGTH:
                candidate = current[: self.MAX_LENGTH - 1].rstrip("，；;：:。！？!?") + "。"
                if len(candidate) >= self.MIN_LENGTH and self.evaluate(candidate, excerpts):
                    return candidate

        first = current if current else (cleaned_candidates[0] if cleaned_candidates else excerpts[0])
        first = self._clean_takeaway_text(first)
        if len(first) > self.MAX_LENGTH:
            cand = first[: self.MAX_LENGTH - 1].rstrip("，；;：:。！？!?") + "。"
            if self.evaluate(cand, excerpts):
                return cand
        elif len(first) >= self.MIN_LENGTH:
            cand = first.rstrip("。！？!?") + "。"
            if self.evaluate(cand, excerpts):
                return cand

        # Fallback: find substantive clauses from excerpts and compose a grounded assertion
        for exc in excerpts:
            clauses = re.split(r"[。！？!?；;\s]+", exc)
            for c in clauses:
                c_clean = self._clean_takeaway_text(c)
                if len(c_clean) >= 10:
                    cand = f"{c_clean}，投資人應持續關注相關市場風險與部位變化。"
                    if len(cand) > self.MAX_LENGTH:
                        cand = cand[: self.MAX_LENGTH - 1].rstrip("，；;：:。！？!?") + "。"
                    if self.MIN_LENGTH <= len(cand) <= self.MAX_LENGTH and self.evaluate(cand, excerpts):
                        return cand

        return "投資人應持續關注市場盤面動態變化並嚴格維持操作紀律。"

    def repair(self, takeaway: str, excerpts: Sequence[str]) -> str:
        """Deterministically repair a flawed takeaway."""
        text = self._clean_takeaway_text(takeaway)

        terminal = text[-1] if text and text[-1] in "。！？!?" else "。"
        text = text.rstrip("。！？!?；;，,") + terminal

        if self.evaluate(text, excerpts):
            return text

        return self.extract_deterministic_takeaway(excerpts)
