"""Transcript processor - Sanitization, segmentation, and feature extraction for podcast transcripts."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence

MAX_EXCERPT_CHARS = 150

SPONSOR_MARKERS = (
    "本集節目由",
    "贊助訊息",
    "贊助播出",
    "專屬優惠碼",
    "專屬的折扣碼",
    "優惠碼",
    "折扣碼",
    "結帳輸入",
    "全站結帳",
    "資訊欄連結",
    "優惠方案",
    "退費保證",
    "購物金",
    "業配",
    "NordVPN",
    "Cybex 兒童安全座椅",
    "Euro NCAP",
    "ADAC 認證",
)


class TranscriptSanitizer:
    """Sanitize raw transcript texts by removing sponsors, recaps, and noise formatting."""

    @staticmethod
    def clean(text: str) -> str:
        """Strip sponsor blocks, intro ads, post-sponsor bridges, recaps, and markdown formatting."""
        # 1. Strip leading sponsor section
        leading_separator = re.search(r"^\s*(?:\*{3,}|-{3,})\s*$", text, flags=re.M)
        if leading_separator and leading_separator.end() <= 5_000:
            leading_block = text[: leading_separator.start()]
            if re.search(r"(?:贊助|讚助|有贊助一個廣告|優惠碼|折扣碼|購物金)", leading_block):
                text = text[leading_separator.end() :]

        # 2. Match sponsor announcements
        sponsor = re.search(
            r"(?:本[集期]節目由.{0,120}?(?:贊助|讚助)|本期節目是由銀座白石.{0,120}?(?:贊助|讚助)|有贊助一個廣告)",
            text[:1000],
            flags=re.S,
        )
        if sponsor:
            tail = text[sponsor.end() :]
            separator = re.search(r"^\s*(?:\*{3,}|-{3,})\s*$", tail, flags=re.M)
            promo_matches = list(
                re.finditer(
                    r"^.*(?:資訊欄|連結欄|折扣碼|優惠碼|官網採購|官方購買|歡迎來電).*$",
                    tail[:10_000],
                    flags=re.M,
                )
            )
            next_heading = re.search(r"^#{2,6}\s+(?!.*(?:贊助|優惠|折扣|產品)).+$", tail, flags=re.M)
            paragraph_end = re.search(r"\n\s*\n", tail)
            special_is_by_form = "節目是由" in sponsor.group()
            terminal_promo = (
                re.search(r"^.*不要錯過.*$", tail[:10_000], flags=re.M)
                if special_is_by_form
                else None
            )
            if special_is_by_form and terminal_promo:
                text = tail[terminal_promo.end() :]
            elif separator and separator.end() <= 10_000:
                text = tail[separator.end() :]
            elif next_heading and next_heading.start() <= 10_000:
                text = tail[next_heading.start() :]
            elif promo_matches:
                text = tail[promo_matches[-1].end() :]
            elif paragraph_end and paragraph_end.end() <= 5_000:
                text = tail[paragraph_end.end() :]

        # 3. Strip post-sponsor bridge
        text = text.lstrip()
        silver_bridge = bool(sponsor and "銀座白石" in sponsor.group() and re.search(r"^唸完前面這個廣告詞", text))
        sony_bridge = bool(sponsor and "Sony WH-1000XM5" in sponsor.group() and re.search(r"^好[，,、 ]*那在這種風雨飄搖.{0,80}Sony.{0,40}抽獎", text, flags=re.S))
        wedding_bridge = bool(re.search(r"^剛剛看到這個婚戒廣告", text))
        if silver_bridge or sony_bridge or wedding_bridge:
            bridge_separator = re.search(r"^\s*(?:\*{3,}|-{3,})\s*$", text[:5_000], flags=re.M)
            bridge_paragraph = re.search(r"\n\s*\n", text[:2_000])
            if bridge_separator:
                text = text[bridge_separator.end() :]
            elif bridge_paragraph:
                text = text[bridge_paragraph.end() :]

        # 4. Strip trailing recap
        recap_patterns = (
            r"^\s*\(後續內容被截斷\)\s*$",
            r"^\s*\*\*本集重點回顧[：:]\*\*\s*$",
            r"^\s*#{1,3}\s*(?:本集)?(?:重點)?(?:回顧|總結)\s*$",
        )
        recap_positions = [m.start() for p in recap_patterns if (m := re.search(p, text, flags=re.M))]
        if recap_positions:
            text = text[: min(recap_positions)]

        # 5. Clean markdown headers, lines, blockquotes, boldings, and URLs
        text = re.sub(r"^#{1,6}\s+.*$", "", text, flags=re.M)
        text = re.sub(r"^\s*(?:-{3,}|\*{3,})\s*$", "", text, flags=re.M)
        text = re.sub(r"^\s*>\s?", "", text, flags=re.M)
        text = text.replace("**", "").replace("__", "")
        text = re.sub(r"https?://\S+", "", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def clean_excerpt(text: str, max_chars: int = MAX_EXCERPT_CHARS) -> str:
        """Clean and normalize a candidate excerpt sentence."""
        text = text.strip().replace("「", "").replace("」", "").replace("『", "").replace("』", "")
        text = re.sub(r"^[#*_>`~\s-]+", "", text)
        text = re.sub(
            r"^(?:那麼|那|所以|然後|其實|當然|我覺得|就是|對啊|好啦|OK|嗯)[，,、\s]*",
            "",
            text,
            flags=re.I,
        )
        text = re.sub(r"\s+", " ", text).strip()
        terminal = text[-1] if text and text[-1] in "。！？!?" else "。"
        if len(text) > max_chars:
            clauses = re.split(r"(?<=[，；;：:])", text)
            kept = ""
            for clause in clauses:
                if len(kept) + len(clause) > max_chars - 1:
                    break
                kept += clause
            if kept:
                return kept.rstrip("，；;：:。！？!?") + "…"
            return text[: max_chars - 1].rstrip("，；;：:。！？!?") + "…"
        return text.rstrip("。！？!?；;") + terminal


from dataclasses import dataclass


@dataclass(frozen=True)
class TextWindow:
    """Represents a semantically coherent window of transcript text."""
    index: int
    text: str
    sentences: tuple[str, ...]
    position: int
    is_qa: bool = False
    topic_hint: str = ""


class TranscriptSegmenter:
    """Segment and chunk transcript texts."""

    def __init__(
        self,
        sanitizer: TranscriptSanitizer | None = None,
        features: TranscriptFeatureExtractor | None = None,
    ) -> None:
        self.sanitizer = sanitizer or TranscriptSanitizer()
        self.features = features or TranscriptFeatureExtractor()

    def detect_qa_boundary(self, text: str) -> int:
        """Detect the starting character index of the Q&A / listener feedback section."""
        qa_patterns = (
            re.compile(r"(?:好[，,、 ]*)?(?:我們|那我|那我先|那接著|接著|那|好啦|OK)?\s*(?:進入|進|切到|切入|開始)(?:\s*(?:QA|Q&A|Q and A|問答|留言|聽眾問答|聽眾QA|Apple Podcast|五星))", re.IGNORECASE),
            re.compile(r"(?:好[，,、 ]*)?(?:接下來|再來|接著|最後)(?:是|看|進入|進)?\s*(?:QA|Q&A|Q and A|問答|聽眾問答|聽眾QA|Apple Podcast 留言|五星留言|留言區|留言的部分)", re.IGNORECASE),
            re.compile(r"(?:好[，,、 ]*)?(?:來看|看|回|回覆|念|唸)(?:一下)?\s*(?:QA|Q&A|Apple Podcast|Podcast|五星吹捧|五星好評|五星留言|聽眾留言|大家(?:的)?留言)", re.IGNORECASE),
            re.compile(r"(?:進入|進|看)?\s*Apple Podcast\s*(?:的)?(?:五星)?留言", re.IGNORECASE),
            re.compile(r"(?:好[，,、 ]*)?第一位(?:朋友|聽眾|留言|是)[，,、 :：]", re.IGNORECASE),
            re.compile(r"(?:好[，,、 ]*)?第一則留言[，,、 :：]", re.IGNORECASE),
        )
        min_pos = int(len(text) * 0.15) if len(text) > 1000 else 0
        earliest_pos = -1
        for pattern in qa_patterns:
            for match in pattern.finditer(text):
                if match.start() >= min_pos:
                    if earliest_pos == -1 or match.start() < earliest_pos:
                        earliest_pos = match.start()
        return earliest_pos

    def segment_sentences(self, text: str) -> list[str]:
        """Clean transcript and split into distinct sentences based on punctuation."""
        cleaned = self.sanitizer.clean(text)
        return [s.strip() for s in re.split(r"(?<=[。！？!?])\s*", cleaned) if s.strip()]

    def segment_sentences_with_offsets(self, cleaned: str) -> list[tuple[str, int]]:
        """Split cleaned text into sentences with start offsets."""
        results: list[tuple[str, int]] = []
        for m in re.finditer(r"[^。！？!?]+[。！？!?]?", cleaned):
            s = m.group().strip()
            if s:
                results.append((s, m.start()))
        return results or ([(cleaned, 0)] if cleaned else [])

    def make_chunks(self, text: str, target: int = 520) -> list[str]:
        """Aggregate sentences into chunks around target character length."""
        result: list[str] = []
        current: list[str] = []
        size = 0
        for s in self.segment_sentences(text):
            if current and size + len(s) > target:
                result.append("".join(current))
                current, size = [], 0
            current.append(s)
            size += len(s)
        if current:
            result.append("".join(current))
        return result

    @staticmethod
    def split_seeds(summary: str) -> list[str]:
        """Split a curated summary into 3–6 topic seed clauses."""
        parts = re.split(
            r"(?<=[。！!])\s*|(?<=[？?])(?![）)])\s*|[；;]|"
            r"(?=(?:接著|市場端|產業端|操作面|投資面|總經面|最後|Q&A|QA))|"
            r"(?=以及(?:試用|分析|討論|觀察|聊))",
            summary,
        )
        parts = [p.strip(" ，、。；;") for p in parts if len(p.strip(" ，、。；;")) >= 12]
        if len(parts) < 3:
            clauses = [p.strip() for p in re.split(r"[，、]", summary) if len(p.strip()) >= 9]
            if clauses:
                group_size = max(1, math.ceil(len(clauses) / 4))
                parts = ["、".join(clauses[i : i + group_size]) for i in range(0, len(clauses), group_size)]
        if len(parts) > 6:
            parts = parts[:5] + ["；".join(parts[5:])]
        return parts or [summary]

    def segment_semantic_chapters(
        self,
        transcript: str,
        target_count: int = 8,
        summary: str = "",
    ) -> list[TextWindow]:
        """Segment transcript into semantically coherent topic windows."""
        cleaned = self.sanitizer.clean(transcript)
        if not cleaned:
            return []

        sent_items = self.segment_sentences_with_offsets(cleaned)
        if not sent_items:
            return []

        summary_seeds = self.split_seeds(summary) if summary else []
        total_sentences = len(sent_items)
        if summary_seeds and len(summary_seeds) <= target_count and total_sentences <= len(summary_seeds) * 4:
            effective_target = len(summary_seeds)
        else:
            effective_target = max(1, min(target_count, max(1, total_sentences // 2)))

        qa_boundary = self.detect_qa_boundary(cleaned)
        if qa_boundary != -1:
            main_items = [(s, pos) for s, pos in sent_items if pos < qa_boundary]
            qa_items = [(s, pos) for s, pos in sent_items if pos >= qa_boundary]
        else:
            main_items = sent_items
            qa_items = []

        if not main_items and qa_items:
            main_items = qa_items
            qa_items = []

        if qa_items:
            main_len = sum(len(s) for s, _ in main_items)
            qa_len = sum(len(s) for s, _ in qa_items)
            total_len = max(1, main_len + qa_len)
            main_target = max(1, round(effective_target * (main_len / total_len)))
            qa_target = max(1, effective_target - main_target)
        else:
            main_target = effective_target
            qa_target = 0

        def partition_items(
            items: list[tuple[str, int]],
            k: int,
            cues_pattern: re.Pattern | None = None,
            min_items_per_group: int = 2,
        ) -> list[list[tuple[str, int]]]:
            if not items:
                return []
            max_k = max(1, len(items) // min_items_per_group)
            k = min(k, max_k)
            if k <= 1 or len(items) <= min_items_per_group:
                return [items]

            split_candidates: list[int] = []
            if cues_pattern:
                for idx, (s, _) in enumerate(items):
                    if idx >= min_items_per_group and (len(items) - idx) >= min_items_per_group:
                        if cues_pattern.search(s):
                            split_candidates.append(idx)

            ideal_chunk = len(items) / k
            splits = [0]
            for step in range(1, k):
                target_idx = int(step * ideal_chunk)
                best_split = -1
                min_dist = float("inf")
                for cand in split_candidates:
                    if cand - splits[-1] >= min_items_per_group and (len(items) - cand) >= (k - step) * min_items_per_group:
                        dist = abs(cand - target_idx)
                        if dist < min_dist:
                            min_dist = dist
                            best_split = cand
                if best_split != -1 and best_split not in splits:
                    splits.append(best_split)
                else:
                    fallback_split = splits[-1] + max(min_items_per_group, round(ideal_chunk))
                    fallback_split = min(fallback_split, len(items) - (k - step) * min_items_per_group)
                    if fallback_split not in splits and fallback_split - splits[-1] >= min_items_per_group:
                        splits.append(fallback_split)
            splits.append(len(items))

            groups: list[list[tuple[str, int]]] = []
            for i in range(len(splits) - 1):
                start, end = splits[i], splits[i + 1]
                if start < end:
                    groups.append(items[start:end])
            return groups

        main_transition_cues = re.compile(
            r"^(?:好[，,、 ]*)?(?:我們(?:第一段|首先)?(?:先)?來聊|接著|另外|再來|第二個|第三個|第四個|第五個|轉向|回到|市場方面|產業方面|操作方面|總經方面|宏觀方面|美股方面|台股方面|晶圓代工|記憶體|伺服器|AI|AI伺服器|散熱)",
            re.IGNORECASE,
        )
        qa_listener_cues = re.compile(
            r"(?:下一位|下一則|這一位|第二位|第三位|第[一二三四五六七八九十]+位|留言說|留言寫道|五星吹捧|五星好評|五星留言|留言的部分|網友問|有朋友問)",
            re.IGNORECASE,
        )

        main_groups = partition_items(main_items, main_target, main_transition_cues)
        qa_groups = partition_items(qa_items, qa_target, qa_listener_cues) if qa_items else []

        all_groups: list[tuple[bool, list[tuple[str, int]]]] = []
        for g in main_groups:
            all_groups.append((False, g))
        for g in qa_groups:
            all_groups.append((True, g))

        used_seeds: set[int] = set()

        windows: list[TextWindow] = []
        for idx, (is_qa, group) in enumerate(all_groups, 1):
            sentences = tuple(s for s, _ in group)
            text_block = "".join(sentences)
            pos = group[0][1] if group else 0

            topic_hint = ""
            if summary_seeds:
                window_features = self.features.features(text_block)
                ranked_seeds = []
                for s_idx, seed in enumerate(summary_seeds):
                    score = self.features.similarity(window_features, self.features.features(seed))
                    if s_idx in used_seeds:
                        score -= 0.1
                    ranked_seeds.append((score, s_idx, seed))
                ranked_seeds.sort(reverse=True)
                if ranked_seeds:
                    best_score, best_idx, best_seed = ranked_seeds[0]
                    used_seeds.add(best_idx)
                    topic_hint = best_seed

            if not topic_hint:
                if is_qa:
                    topic_hint = f"聽眾問答與互動交流 第{idx}部分"
                else:
                    topic_hint = sentences[0][:30] if sentences else ""

            windows.append(
                TextWindow(
                    index=idx,
                    text=text_block,
                    sentences=sentences,
                    position=pos,
                    is_qa=is_qa,
                    topic_hint=topic_hint,
                )
            )

        return windows


class TranscriptFeatureExtractor:
    """Extract lexical features and compute text similarity."""

    @staticmethod
    def features(text: str) -> Counter[str]:
        """Extract alphanumeric tokens and Chinese character n-grams with weights."""
        compact = re.sub(r"\s+", "", text.lower())
        res: Counter[str] = Counter()
        for token in re.findall(r"[a-z][a-z0-9.+-]{1,}|\d+(?:\.\d+)?", compact):
            res[token] += 5
        chinese = "".join(re.findall(r"[\u3400-\u9fff]", compact))
        for size, weight in ((2, 1), (3, 2)):
            for i in range(len(chinese) - size + 1):
                res[chinese[i : i + size]] += weight
        return res

    @staticmethod
    def similarity(left: Counter[str], right: Counter[str]) -> float:
        """Calculate weighted overlap ratio between two feature bags."""
        if not left or not right:
            return 0.0
        overlap = sum(min(weight, right.get(term, 0)) for term, weight in left.items())
        return overlap / max(1, sum(left.values()))
