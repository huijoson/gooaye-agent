#!/usr/bin/env python3
"""Heading Quality Engine - Deep module for evaluating, diagnosing, and repairing chapter headings."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class DefectCategory(str, Enum):
    FORMAT = "format"
    GENERIC_TERMS = "generic_terms"
    TRANSITION_PREFIX = "transition_prefix"
    CONVERSATIONAL_FRAGMENT = "conversational_fragment"
    MACHINE_GLUE = "machine_glue"
    SUMMARY_LEAKAGE = "summary_leakage"
    WEAK_GROUNDING = "weak_grounding"
    BROKEN_LATIN = "broken_latin"
    UNBALANCED_SYNTAX = "unbalanced_syntax"


@dataclass(frozen=True)
class Defect:
    category: DefectCategory
    message: str
    trigger: str = ""


@dataclass(frozen=True)
class QualityReport:
    heading: str
    defects: tuple[Defect, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        return len(self.defects) == 0

    @property
    def feedback_message(self) -> str:
        if self.is_valid:
            return "合格"
        return "；".join(d.message for d in self.defects)


class HeadingQualityEngine:
    """Deep module encapsulating all chapter heading quality evaluation, defect diagnostics, and deterministic repair."""

    MIN_LENGTH = 8
    MAX_LENGTH = 36

    GENERIC_PATTERN = re.compile(
        r"(?:主題|其他|雜談|市場話題|聽眾問答|實務建議|本段重點|問答時段|Q\s*&?\s*A|問答|回答聽眾|這件事情|這個東西|沒有辦法|就是這樣)",
        re.IGNORECASE,
    )

    BAD_PREFIX_PATTERN = re.compile(
        r"^(?:另外|另|順帶|接著|轉向|轉入|並|後半|後段|還有|同時|的|了|是|個|些|或是|應該|不一定|直接|這個|這些|一個|比較|裡面|後面|像我|像是|像|那麼|那|不是只是|剛好|大概|其實|不過)"
    )

    FRAGMENT_SUFFIX_PATTERN = re.compile(
        r"(?:去與|來與|說與|的與|事情與|一個與|就是與|[`]|<seg|[…]{2,}|[，,、—-]$)",
        re.IGNORECASE,
    )

    ORAL_DIRECT_PATTERN = re.compile(
        r"(?:我|你|我們|你們|人家|大家互相|問我|跟我說|我覺得|我認為|就覺得|覺得|認為|搞不好|的時候|而已|滿抖|超大|超多|超狂|超鬧|超香|爛透|蠻多|真抖|剛好打到|錯過東西|好東西|很多東西|多試幾次|120 幾|\d+ 幾|花費是|Zoom 是)"
    )

    ORAL_WORDS_PATTERN = re.compile(
        r"(?:^|[^A-Za-z])(?:我|你|他|它|人家|別人|大家|就是|說|講|覺得|認為|搞不好|像是|這個|那個|東西|事情|狀況|樣子|的時候|而已|而且|其實|真的|蠻|滿抖|超大|超多)"
    )

    SPLIT_PATTERN = re.compile(
        r"[，。！？!?；;：:]|(?:但是|可是|不過|所以|然後|其實|當然|因為|如果|就是|等於說|換句話說|來說|的話|包含|包括|以及|而且|反正|我覺得|我認為|可能|大概|首先|再來|最後|接下來)"
    )

    LEADING_TRIM_PATTERN = re.compile(
        r"^(?:像我|像是|像|那麼|那|這個|這些|這種|有一個|一個|我們|你知道|譬如說|例如說|例如|目前|現在|今天|這次|就|都|也|還|又|會|可以|要|去)+"
    )

    TRAILING_TRIM_PATTERN = re.compile(
        r"(?:這樣|這件事|這個東西|的部分|的地方|的情形|的狀況|的問題|的事情|之類的|而已|啦|嘛|吧|呢|喔|啊)+$"
    )

    GENERIC_PARTS_PATTERN = re.compile(
        r"^(?:跟大家分享|不知道|沒有辦法|非常重要|一樣的東西|很多東西|這是什麼|怎麼樣做|做這件事|看這件事)$"
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

    CONNECTORS = ("與", "及", "對照", "並談")

    def __init__(self, corpus_frequencies: Counter[str] | None = None) -> None:
        self.frequencies = corpus_frequencies or Counter()

    @staticmethod
    def compact(text: str) -> str:
        return "".join(re.findall(r"[\u3400-\u9fffa-zA-Z0-9]+", text)).lower()

    @staticmethod
    def compact_with_map(text: str) -> tuple[str, list[int]]:
        chars, positions = [], []
        for index, char in enumerate(text):
            if re.match(r"[\u3400-\u9fffa-zA-Z0-9]", char):
                chars.append(char.lower())
                positions.append(index)
        return "".join(chars), positions

    @staticmethod
    def bigrams(text: str) -> set[str]:
        value = HeadingQualityEngine.compact(text)
        return {value[i : i + 2] for i in range(len(value) - 1)}

    @staticmethod
    def ngrams(text: str, n: int) -> set[str]:
        value = HeadingQualityEngine.compact(text)
        return {value[i : i + n] for i in range(len(value) - n + 1)}

    def diagnose(
        self,
        heading: str,
        excerpts: Sequence[str],
        summary: str = "",
    ) -> QualityReport:
        """Perform complete defect diagnostic analysis on a chapter heading candidate."""
        defects: list[Defect] = []
        heading = heading.strip()
        h_compact = self.compact(heading)

        # 1. Format & length checks
        if not self.MIN_LENGTH <= len(heading) <= self.MAX_LENGTH:
            defects.append(
                Defect(
                    DefectCategory.FORMAT,
                    f"標題字數應在 {self.MIN_LENGTH}–{self.MAX_LENGTH} 字之間（目前 {len(heading)} 字）",
                    f"length={len(heading)}",
                )
            )

        if "…" in heading or "..." in heading:
            defects.append(
                Defect(
                    DefectCategory.FORMAT,
                    "標題不可包含省略號（…）",
                    "ellipsis",
                )
            )

        for open_sym, close_sym in self.PAIRED_SYMBOLS:
            if heading.count(open_sym) != heading.count(close_sym):
                defects.append(
                    Defect(
                        DefectCategory.UNBALANCED_SYNTAX,
                        f"符號未成對：{open_sym}{close_sym}",
                        f"unbalanced_{open_sym}{close_sym}",
                    )
                )

        if self.FRAGMENT_SUFFIX_PATTERN.search(heading):
            defects.append(
                Defect(
                    DefectCategory.FORMAT,
                    "標題包含殘缺標點、連詞殘片或語法碎片",
                    "fragment_syntax",
                )
            )

        # Multiple connectors check (e.g. A與B與C)
        if sum(heading.count(conn) for conn in self.CONNECTORS) >= 2:
            defects.append(
                Defect(
                    DefectCategory.MACHINE_GLUE,
                    "標題出現多次連詞（如多個「與」），語法串接冗長",
                    "multiple_connectors",
                )
            )

        # 2. Generic terms & transition prefixes
        generic_match = self.GENERIC_PATTERN.search(heading)
        if generic_match:
            defects.append(
                Defect(
                    DefectCategory.GENERIC_TERMS,
                    f"標題包含空泛泛稱詞（{generic_match.group()}）",
                    "generic_term",
                )
            )

        prefix_match = self.BAD_PREFIX_PATTERN.search(heading)
        if prefix_match:
            defects.append(
                Defect(
                    DefectCategory.TRANSITION_PREFIX,
                    f"標題不可使用過渡詞或助詞開頭（{prefix_match.group()}）",
                    "bad_prefix",
                )
            )

        # 3. Grounding & Excerpt Coverage
        if excerpts:
            h_bigrams = self.bigrams(heading)
            for idx, bullet in enumerate(excerpts, 1):
                b_bigrams = self.bigrams(bullet)
                if not (h_bigrams & b_bigrams):
                    defects.append(
                        Defect(
                            DefectCategory.WEAK_GROUNDING,
                            f"標題未有效涵蓋摘錄 {idx} 的核心詞彙",
                            f"weak_bullet_{idx}",
                        )
                    )

        # 4. Summary Isolation (Leakage check)
        if summary:
            s_compact = self.compact(summary)
            if len(h_compact) >= 5 and h_compact in s_compact:
                defects.append(
                    Defect(
                        DefectCategory.SUMMARY_LEAKAGE,
                        "標題完全照抄第三方摘要，違反逐字稿接地原則",
                        "full_summary_copy",
                    )
                )
            else:
                e_compact = self.compact(" ".join(excerpts))
                for i in range(max(0, len(h_compact) - 5)):
                    gram = h_compact[i : i + 6]
                    if gram in s_compact and gram not in e_compact:
                        defects.append(
                            Defect(
                                DefectCategory.SUMMARY_LEAKAGE,
                                "標題包含僅出現在第三方摘要而未在逐字稿出現的詞彙",
                                "summary_only_vocab",
                            )
                        )
                        break

        # 5. Conversational slice (Oral fragment check)
        if self.ORAL_DIRECT_PATTERN.search(heading):
            match = self.ORAL_DIRECT_PATTERN.search(heading)
            defects.append(
                Defect(
                    DefectCategory.CONVERSATIONAL_FRAGMENT,
                    f"標題保留口語人稱或對話語氣（{match.group() if match else ''}）",
                    "oral_direct_phrase",
                )
            )
        elif excerpts:
            e_compact_list = [self.compact(b) for b in excerpts]
            parts = [heading]
            for conn in self.CONNECTORS:
                parts.extend(p for p in heading.split(conn) if p)
            for part in parts:
                p_compact = self.compact(part)
                if len(p_compact) >= 8 and self.ORAL_WORDS_PATTERN.search(part):
                    if any(p_compact in e for e in e_compact_list):
                        defects.append(
                            Defect(
                                DefectCategory.CONVERSATIONAL_FRAGMENT,
                                f"標題保留逐字稿長口語句片段（{part}）",
                                "oral_raw_slice",
                            )
                        )
                        break

        # 6. Machine Glue Check (long unedited clause slices spliced with connector)
        if excerpts and len(excerpts) >= 2:
            b1_compact, b2_compact = self.compact(excerpts[0]), self.compact(excerpts[1])
            for conn in self.CONNECTORS:
                for match in re.finditer(conn, heading):
                    left = self.compact(heading[: match.start()])
                    right = self.compact(heading[match.end() :])
                    if len(left) >= 12 and len(right) >= 12:
                        if (left in b1_compact and right in b2_compact) or (
                            left in b2_compact and right in b1_compact
                        ):
                            defects.append(
                                Defect(
                                    DefectCategory.MACHINE_GLUE,
                                    f"以連詞「{conn}」機械拼接兩段長逐字句，缺少概念概括",
                                    "machine_glue",
                                )
                            )
                            break

        # 7. Broken Latin check (Cut-off English words)
        if excerpts:
            evidence_text = " ".join(excerpts)
            ev_tokens = [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9.+-]*", evidence_text)]
            ev_token_set = set(ev_tokens)
            cleaned_ev_set = {t.replace("-", "") for t in ev_tokens}
            for token in re.findall(r"[A-Za-z][A-Za-z0-9.+-]*", heading):
                t = token.lower()
                if t in ev_token_set or t.replace("-", "") in cleaned_ev_set:
                    continue
                if any(len(t) >= 3 and ev.startswith(t) and t != ev for ev in ev_tokens):
                    defects.append(
                        Defect(
                            DefectCategory.BROKEN_LATIN,
                            f"英文字詞或專名遭截斷（{token}）",
                            f"broken_latin_{token}",
                        )
                    )
                    break

        return QualityReport(heading=heading, defects=tuple(defects))

    def evaluate(
        self,
        heading: str,
        excerpts: Sequence[str],
        summary: str = "",
    ) -> bool:
        """Fast boolean gate for heading validity."""
        return self.diagnose(heading, excerpts, summary).is_valid

    def extract_phrase_candidates(
        self,
        text: str,
        guide: str = "",
    ) -> list[str]:
        """Extract natural, meaningful candidate phrases from an excerpt for deterministic composition."""
        raw_parts = [part.strip(" 、-—()（）[]【】") for part in self.SPLIT_PATTERN.split(text)]
        candidates = []
        for raw in raw_parts:
            part = self.LEADING_TRIM_PATTERN.sub("", raw).strip()
            part = self.TRAILING_TRIM_PATTERN.sub("", part).strip()
            value = self.compact(part)
            if len(value) < 3 or self.GENERIC_PARTS_PATTERN.fullmatch(part):
                continue
            if len(part) <= 12:
                candidates.append(part)
            else:
                subparts = [
                    p.strip()
                    for p in re.split(r"(?:，|、|與|以及|還有|並且|並|而|但|卻)", part)
                    if 3 <= len(self.compact(p.strip())) <= 12
                ]
                candidates.extend(subparts)
                guide_value = self.compact(guide)
                part_value = self.compact(part)
                shared = []
                for size in range(min(10, len(guide_value), len(part_value)), 1, -1):
                    shared = [
                        guide_value[i : i + size]
                        for i in range(len(guide_value) - size + 1)
                        if guide_value[i : i + size] in part_value
                    ]
                    if shared:
                        break
                if shared:
                    token = shared[0]
                    pos = part_value.find(token)
                    start = max(0, pos - 2)
                    candidates.append(part[start : start + min(10, len(part) - start)].strip())

        if not candidates:
            val = text.strip(" 。！？!?，；;：:")
            candidates = [val[:10].rstrip("，；;：:")]

        unique = []
        seen = set()
        guide_bigrams = self.bigrams(guide) if guide else set()
        for candidate in candidates:
            candidate = candidate.strip(" ，、。；;：:-—")
            val = self.compact(candidate)
            if not 3 <= len(val) <= 14 or val in seen:
                continue
            if self.ORAL_DIRECT_PATTERN.search(candidate) or self.BAD_PREFIX_PATTERN.search(candidate):
                continue
            seen.add(val)
            unique.append(candidate)

        def score(candidate: str) -> float:
            val = self.compact(candidate)
            grams = [val[i : i + 4] for i in range(max(0, len(val) - 3))]
            rarity = sum(1 / math.sqrt(self.frequencies.get(gram, 1)) for gram in grams)
            overlap = len(self.bigrams(candidate) & guide_bigrams) if guide_bigrams else 0
            named = 2.0 if re.search(r"[A-Za-z0-9]", candidate) else 0.0
            return overlap * 5 + rarity + named + min(len(val), 10) * 0.08

        return sorted(unique, key=score, reverse=True)

    def repair(
        self,
        heading: str,
        excerpts: Sequence[str],
        summary: str = "",
        used_headings: set[str] | None = None,
    ) -> str:
        """Deterministically repair or synthesize a valid heading from both excerpts."""
        used = used_headings if used_headings is not None else set()
        if len(excerpts) < 2:
            raise ValueError("Repair requires at least two excerpts")

        report = self.diagnose(heading, excerpts, summary)
        if report.is_valid and self.compact(heading) not in used:
            return heading

        one = self.extract_phrase_candidates(excerpts[0], heading)
        two = self.extract_phrase_candidates(excerpts[1], heading)

        # Strategy A: If only one excerpt has weak grounding, try appending a natural phrase
        weak_reasons = [d for d in report.defects if d.category == DefectCategory.WEAK_GROUNDING]
        non_weak = [d for d in report.defects if d.category != DefectCategory.WEAK_GROUNDING]
        if weak_reasons and not non_weak:
            candidate = heading
            triggers = {d.trigger for d in weak_reasons}
            if "weak_bullet_1" in triggers and one:
                candidate = f"{one[0]}與{candidate}"
            if "weak_bullet_2" in triggers and two:
                candidate = f"{candidate}與{two[0]}"
            candidate = re.sub(r"(?:分析|探討|觀點|說明|提醒|介紹)$", "", candidate)
            if self.compact(candidate) not in used and self.evaluate(candidate, excerpts, summary):
                return candidate

        # Strategy B: Compose pairwise combinations from top phrase candidates
        for p1 in one[:10]:
            for p2 in two[:10]:
                options = (
                    [p1]
                    if self.compact(p1) == self.compact(p2)
                    else [
                        f"{p1}與{p2}",
                        f"{p1}及{p2}",
                        f"{p1}對照{p2}",
                        f"{p1}並談{p2}",
                    ]
                )
                for cand in options:
                    cand = re.sub(r"\s+", " ", cand).strip()
                    if self.compact(cand) not in used and self.evaluate(cand, excerpts, summary):
                        return cand

        # Fallback Strategy C: Truncate and stitch with clean connector
        c1 = one[0] if one else excerpts[0][:8].strip()
        c2 = two[0] if two else excerpts[1][:8].strip()
        fallback = f"{c1}與{c2}"[: self.MAX_LENGTH]
        return fallback
