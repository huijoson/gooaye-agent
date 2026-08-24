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


class TranscriptSegmenter:
    """Segment and chunk transcript texts."""

    def __init__(self, sanitizer: TranscriptSanitizer | None = None) -> None:
        self.sanitizer = sanitizer or TranscriptSanitizer()

    def segment_sentences(self, text: str) -> list[str]:
        """Clean transcript and split into distinct sentences based on punctuation."""
        cleaned = self.sanitizer.clean(text)
        return [s.strip() for s in re.split(r"(?<=[。！？!?])\s*", cleaned) if s.strip()]

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
