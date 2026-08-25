#!/usr/bin/env python3
"""Heading Quality Engine - Deep module for evaluating, diagnosing, and repairing chapter headings."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence

from domain import DefectCategory, Defect, QualityReport


class HeadingQualityEngine:
    """Deep module encapsulating all chapter heading quality evaluation, defect diagnostics, and deterministic repair."""

    MIN_LENGTH = 8
    MAX_LENGTH = 36

    GENERIC_PATTERN = re.compile(
        r"(?:主題|其他|雜談|市場話題|聽眾問答|實務建議|本段重點|問答時段|Q\s*&?\s*A|問答|回答聽眾|這件事情|這個東西|沒有辦法|就是這樣)",
        re.IGNORECASE,
    )

    BAD_PREFIX_PATTERN = re.compile(
        r"^(?:另外|另|順帶|接著|轉向|轉入|並|後半|後段|還有|同時|的|了|是|個|些|或是|應該|不一定|直接|這個|這些|一個|比較|裡面|後面|像我|像是|像|那麼|那|不是只是|剛好|大概|其實|不過|甚至是在|之前|上一集|順便|希望大家)"
    )

    FRAGMENT_SUFFIX_PATTERN = re.compile(
        r"(?:去與|來與|說與|的與|事情與|一個與|就是與|的東與|[`]|<seg|[…]{2,}|[，,、—\-\s]$)",
        re.IGNORECASE,
    )

    ORAL_DIRECT_PATTERN = re.compile(
        r"(?:我|你|我們|你們|人家|大家互相|問我|跟我說|我覺得|我認為|就覺得|覺得|認為|搞不好|的時候|而已|滿抖|超大|超多|超狂|超鬧|超香|爛透|蠻多|真抖|剛好打到|錯過東西|好東西|很多東西|多試幾次|120 幾|\d+ 幾|花費是|Zoom 是)"
    )

    ORAL_WORDS_PATTERN = re.compile(
        r"(?:^|[^A-Za-z])(?:我|你|他|她|它|你們|他們|人家|別人|大家|就是|說|講|覺得|認為|搞不好|像是|這個|那個|東西|事情|狀況|樣子|的時候|而已|而且|其實|真的|蠻|滿抖|超大|超多)"
    )

    SPLIT_PATTERN = re.compile(
        r"[，。！？!?；;：:,、]|[—-]+|(?:但是|可是|不過|所以|然後|其實|當然|因為|如果|就是|等於說|換句話說|來說|的話|包含|包括|以及|而且|反正|我覺得|我認為|可能|大概|首先|再來|最後|接下來|有時候|現這個|希望大家|成為|作為|導致|引發|造成|使得)"
    )

    LEADING_TRIM_PATTERN = re.compile(
        r"^(?:我們|你們|他們|大家|人家|像我|像是|你知道|譬如說|例如說|甚至是在|已經是在|他們要去|希望大家|是來幫大家|幫大家|感謝主委|謝謝主委|感謝|謝謝|祝主委|祝大家|祝|反正總之|反正|總之|也是|就是|而且|甚至|之前|上一集|順便|已經|把那個|去把|整天|當然要|那種|這個|這些|這種|有一個|一個|那麼|像|我|你|他|她|它|們|就|都|也|還|又|會|可以|要|去|來|說|講|看|進去|寫了|把|在|成|為|讓|將|以|對|與|及|真的|或許|可能|大概|其實|不過|的|給)+",
        re.IGNORECASE,
    )

    TRAILING_TRIM_PATTERN = re.compile(
        r"(?:這樣子的支持|這樣子的|這樣子|這件事|這個東西|的部分|的地方|的情形|的狀況|的問題|的事情|之類的|而已|啦|嘛|吧|呢|喔|啊|了|的|過|在|去|來|講|說|的話|的時候|之後|之前|出來|進去|起來|下去|上去|那個|這個|東|成|為|的人|之處|我們|你們|他們|大家|這樣|支持)+$",
        re.IGNORECASE,
    )

    GENERIC_PARTS_PATTERN = re.compile(
        r"^(?:跟大家分享|不知道|沒有辦法|非常重要|一樣的東西|很多東西|這是什麼|怎麼樣做|做這件事|看這件事|QA|Q&A|問答|雜談|其他)$",
        re.IGNORECASE,
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

        # 3. Grounding & Excerpt Coverage (checked against primary excerpts)
        if excerpts:
            h_bigrams = self.bigrams(heading)
            for idx, bullet in enumerate(excerpts[:2], 1):
                b_bigrams = self.bigrams(bullet)
                if not (h_bigrams & b_bigrams):
                    defects.append(
                        Defect(
                            DefectCategory.WEAK_GROUNDING,
                            f"標題未有效涵蓋核心摘錄 {idx} 的詞彙",
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

    def _clean_candidate_phrase(self, raw: str) -> str:
        """Clean leading/trailing oral phrases, punctuation, and avoid cutting Latin words."""
        part = raw.strip(" ，、。；;：:,.-—()（）[]【】《》「」『』\"' ")
        part = self.LEADING_TRIM_PATTERN.sub("", part).strip()
        part = self.TRAILING_TRIM_PATTERN.sub("", part).strip()
        part = self.LEADING_TRIM_PATTERN.sub("", part).strip()
        part = part.strip(" ，、。；;：:,.-—()（）[]【】《》「」『』\"' ")

        # Ensure quotes/brackets in phrase are balanced or stripped
        for open_sym, close_sym in self.PAIRED_SYMBOLS:
            if part.count(open_sym) != part.count(close_sym):
                part = part.replace(open_sym, "").replace(close_sym, "")

        return part.strip(" ，、。；;：:,.-— ")

    def extract_phrase_candidates(
        self,
        text: str,
        guide: str = "",
    ) -> list[str]:
        """Extract natural, meaningful candidate phrases from an excerpt for deterministic composition."""
        raw_parts = [part for part in self.SPLIT_PATTERN.split(text) if part.strip()]
        candidates = []
        for raw in raw_parts:
            part = self._clean_candidate_phrase(raw)
            value = self.compact(part)
            if len(value) < 3 or self.GENERIC_PARTS_PATTERN.fullmatch(part):
                continue
            if len(part) <= 11:
                candidates.append(part)
            else:
                subparts = [
                    self._clean_candidate_phrase(p)
                    for p in re.split(r"(?:，|、|與|以及|還有|並且|並|而|但|卻)", part)
                ]
                for sp in subparts:
                    if 3 <= len(self.compact(sp)) <= 11 and not self.GENERIC_PARTS_PATTERN.fullmatch(sp):
                        candidates.append(sp)

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
                    extracted = part[start : start + min(10, len(part) - start)]
                    cleaned_extracted = self._clean_candidate_phrase(extracted)
                    if 3 <= len(self.compact(cleaned_extracted)) <= 11:
                        candidates.append(cleaned_extracted)

                # Sliding window spans
                for span_len in (4, 6, 8, 10):
                    for start_idx in range(0, max(1, len(part) - span_len + 1), 2):
                        sub = self._clean_candidate_phrase(part[start_idx : start_idx + span_len])
                        if 3 <= len(self.compact(sub)) <= 11 and not self.GENERIC_PARTS_PATTERN.fullmatch(sub):
                            candidates.append(sub)

        # Latin word boundary safety
        latin_words = re.findall(r"[A-Za-z][A-Za-z0-9.+-]*", text)
        latin_word_map = {w[: len(w) - 1].lower(): w for w in latin_words if len(w) >= 3}
        latin_word_map.update({w[: len(w) - 2].lower(): w for w in latin_words if len(w) >= 4})

        unique = []
        seen = set()
        guide_bigrams = self.bigrams(guide) if guide else set()
        for candidate in candidates:
            candidate = self._clean_candidate_phrase(candidate)
            # Fix any truncated latin word at the end/beginning
            for trunc, full in latin_word_map.items():
                if candidate.lower().endswith(trunc) and not candidate.lower().endswith(full.lower()):
                    candidate = candidate[: len(candidate) - len(trunc)] + full

            val = self.compact(candidate)
            if not 3 <= len(val) <= 11 or val in seen:
                continue
            if self.ORAL_DIRECT_PATTERN.search(candidate) or self.BAD_PREFIX_PATTERN.search(candidate):
                continue
            if self.GENERIC_PATTERN.search(candidate) or self.FRAGMENT_SUFFIX_PATTERN.search(candidate):
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
        for p1 in one[:15]:
            for p2 in two[:15]:
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

        # Strategy C: Exhaustive n-gram scan over clean tokens from excerpts
        clean_tokens_1 = [
            self._clean_candidate_phrase(t)
            for t in re.split(r"[，。！？!?；;：:,、\s]+", excerpts[0])
        ]
        clean_tokens_1 = [
            t for t in clean_tokens_1
            if 3 <= len(self.compact(t)) <= 12
            and not self.ORAL_DIRECT_PATTERN.search(t)
            and not self.BAD_PREFIX_PATTERN.search(t)
            and not self.GENERIC_PATTERN.search(t)
        ]
        clean_tokens_2 = [
            self._clean_candidate_phrase(t)
            for t in re.split(r"[，。！？!?；;：:,、\s]+", excerpts[1])
        ]
        clean_tokens_2 = [
            t for t in clean_tokens_2
            if 3 <= len(self.compact(t)) <= 12
            and not self.ORAL_DIRECT_PATTERN.search(t)
            and not self.BAD_PREFIX_PATTERN.search(t)
            and not self.GENERIC_PATTERN.search(t)
        ]
        for t1 in clean_tokens_1:
            for t2 in clean_tokens_2:
                for cand in (f"{t1}與{t2}", f"{t1}及{t2}", f"{t1}對照{t2}"):
                    if self.compact(cand) not in used and self.evaluate(cand, excerpts, summary):
                        return cand

        # Strategy D: Try clean candidates with natural suffix
        for t1 in one + clean_tokens_1:
            for t2 in two + clean_tokens_2:
                cand = f"{t1}與{t2}"[: self.MAX_LENGTH]
                if self.compact(cand) not in used and self.evaluate(cand, excerpts, summary):
                    return cand

        # Fallback Strategy E: Safe guarantee grounded in excerpts
        for exc1 in excerpts:
            t1_list = self.extract_phrase_candidates(exc1)
            for exc2 in excerpts:
                if exc1 == exc2 and len(excerpts) > 1:
                    continue
                t2_list = self.extract_phrase_candidates(exc2)
                for t1 in t1_list:
                    for t2 in t2_list:
                        for cand in (f"{t1}與{t2}", f"{t1}及{t2}", f"{t1}對照{t2}"):
                            if len(cand) <= self.MAX_LENGTH and self.compact(cand) not in used and self.evaluate(cand, excerpts, summary):
                                return cand

        # Ultimate fallback: Construct clean topic assertion from top entities
        for exc in excerpts:
            nouns = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{3,8}", exc)
            for n in nouns:
                if not self.ORAL_WORDS_PATTERN.search(n) and not self.BAD_PREFIX_PATTERN.search(n) and not self.GENERIC_PATTERN.search(n):
                    cand = f"{n}市場趨勢與實務觀點"
                    if self.MIN_LENGTH <= len(cand) <= self.MAX_LENGTH and self.compact(cand) not in used and self.evaluate(cand, excerpts, summary):
                        return cand

        # Safe default
        return "市場動態變化與投資觀念"
