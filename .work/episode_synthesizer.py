#!/usr/bin/env python3
"""Episode Note Synthesizer - Deep module for transcript processing, chapter extraction, heading resolution, and Markdown note synthesis."""

from __future__ import annotations

import json
import math
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol, Sequence
from urllib.parse import quote

from heading_quality_engine import HeadingQualityEngine

ROOT = Path(__file__).resolve().parent.parent
CHANNEL_PATH = ROOT / ".work/channel.json"
ARCHIVE_PATH = ROOT / ".work/source/episodes.json"
TRANSCRIPT_DIR = ROOT / ".work/full-transcripts"
HEADINGS_CACHE_DIR = ROOT / ".work/grounded-headings"
OUTPUT_DIR = ROOT / "gooaye-youtube-notes"
EPISODES_DIR = OUTPUT_DIR / "episodes"
CHANNEL_URL = "https://www.youtube.com/@Gooaye/videos"
ARCHIVE_BASE_URL = "https://whatmkreallysaid.com/"
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


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "未知"
    seconds = round(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def parse_episode_number(title: str) -> int | None:
    match = re.search(r"\bEP\s*(\d+)\b", title, re.IGNORECASE)
    return int(match.group(1)) if match else None


@dataclass(frozen=True)
class Chapter:
    index: int
    heading: str
    excerpts: tuple[str, str]
    position: int = 0


@dataclass(frozen=True)
class EpisodeMetadata:
    number: int
    youtube_id: str
    youtube_url: str
    youtube_title: str
    display_title: str
    date: str
    date_source: str
    duration_str: str
    duration_seconds: int
    archive_url: str
    summary: str


@dataclass(frozen=True)
class EpisodeNote:
    metadata: EpisodeMetadata
    chapters: tuple[Chapter, ...]

    def render_markdown(self) -> str:
        chapter_markdown = []
        for ch in self.chapters:
            bullets = "\n".join(f"- {bullet}" for bullet in ch.excerpts)
            chapter_markdown.append(f"### {ch.index}. {ch.heading}\n\n{bullets}")

        return f"""---
episode: {self.metadata.number}
title: {yaml_string(self.metadata.display_title)}
youtube_title: {yaml_string(self.metadata.youtube_title)}
youtube_id: {yaml_string(self.metadata.youtube_id)}
youtube_url: {yaml_string(self.metadata.youtube_url)}
episode_date: {yaml_string(self.metadata.date)}
episode_date_source: {yaml_string(self.metadata.date_source)}
duration: {yaml_string(self.metadata.duration_str)}
content_method: {yaml_string("extractive_from_full_transcript")}
---

# EP{self.metadata.number}｜{self.metadata.display_title}

- **YouTube 原始標題：** {self.metadata.youtube_title}
- **節目日期：** {self.metadata.date}
- **片長：** {self.metadata.duration_str}
- **影片：** [YouTube]({self.metadata.youtube_url})

## 章節觀念

{chr(10).join(chr(10) + ch for ch in chapter_markdown)}

## 資料來源與整理方式

- 影片資訊：[Gooaye 股癌 YouTube]({self.metadata.youtube_url})
- 完整內容依據：[公開非官方逐字稿]({self.metadata.archive_url})
- 頁首策展標題來自第三方逐字稿索引；YouTube 原始標題另列於上方。
- 第三方摘要只作全文檢索提示；章節按入選摘錄在**完整逐字稿**中的實際位置排序。命名模型只接收每章兩段全文摘錄，不接收摘要；摘要只在事後用來拒絕撞句，少數未通過自動驗證的標題由人工直接依兩段摘錄覆核。條列也是全文短摘錄，而非摘要切片。
- 節目日期主要取自第三方逐字稿索引；若該欄缺漏，才使用單支 YouTube metadata。日期不宣稱等同 YouTube 上傳日。
- 本文沒有虛構時間碼。非官方逐字稿可能有聽寫或專有名詞錯誤，請以原始影片為準。
- 本文僅供學習與索引，不構成投資建議。
"""


@dataclass(frozen=True)
class SynthesisSummary:
    total_episodes: int
    total_chapters: int
    total_seconds: int
    chapter_distribution: Counter[int]
    notes: tuple[EpisodeNote, ...] = field(default_factory=tuple)


class HeadingResolver(Protocol):
    def resolve(
        self,
        metadata: EpisodeMetadata,
        raw_chapters: Sequence[dict],
    ) -> list[str]: ...


class CachedHeadingResolver:
    """Load headings from local cache directory with quality validation."""

    def __init__(
        self,
        cache_dir: Path = HEADINGS_CACHE_DIR,
        quality_engine: HeadingQualityEngine | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.quality = quality_engine or HeadingQualityEngine()

    def resolve(
        self,
        metadata: EpisodeMetadata,
        raw_chapters: Sequence[dict],
    ) -> list[str] | None:
        cache_path = self.cache_dir / f"EP{metadata.number:04d}.json"
        if not cache_path.exists():
            return None
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            headings = data.get("headings")
            if data.get("episode") != metadata.number or not isinstance(headings, list):
                return None
            if len(headings) != len(raw_chapters):
                return None
            for heading, ch in zip(headings, raw_chapters):
                if not self.quality.evaluate(heading, ch["excerpts"], metadata.summary):
                    return None
            return [h.strip() for h in headings]
        except Exception:
            return None


class DeterministicHeadingResolver:
    """Synthesize headings purely in memory using HeadingQualityEngine."""

    def __init__(self, quality_engine: HeadingQualityEngine | None = None) -> None:
        self.quality = quality_engine or HeadingQualityEngine()

    def resolve(
        self,
        metadata: EpisodeMetadata,
        raw_chapters: Sequence[dict],
    ) -> list[str]:
        headings: list[str] = []
        used: set[str] = set()
        for ch in raw_chapters:
            title = self.quality.repair(
                ch.get("title", ""),
                ch["excerpts"],
                metadata.summary,
                used_headings=used,
            )
            headings.append(title)
            used.add(self.quality.compact(title))
        return headings


class CompositeHeadingResolver:
    """Composite resolver: Disk Cache primary -> Deterministic fallback."""

    def __init__(
        self,
        cache_resolver: CachedHeadingResolver | None = None,
        deterministic_resolver: DeterministicHeadingResolver | None = None,
        quality_engine: HeadingQualityEngine | None = None,
    ) -> None:
        quality = quality_engine or HeadingQualityEngine()
        self.cache = cache_resolver or CachedHeadingResolver(quality_engine=quality)
        self.deterministic = deterministic_resolver or DeterministicHeadingResolver(quality_engine=quality)

    def resolve(
        self,
        metadata: EpisodeMetadata,
        raw_chapters: Sequence[dict],
    ) -> list[str]:
        cached = self.cache.resolve(metadata, raw_chapters)
        if cached is not None:
            return cached
        return self.deterministic.resolve(metadata, raw_chapters)


class EpisodeNoteSynthesizer:
    """Deep module orchestrating transcript cleaning, evidence extraction, heading resolution, and Markdown synthesis."""

    def __init__(
        self,
        channel_path: Path = CHANNEL_PATH,
        archive_path: Path = ARCHIVE_PATH,
        transcript_dir: Path = TRANSCRIPT_DIR,
        resolver: HeadingResolver | None = None,
        quality_engine: HeadingQualityEngine | None = None,
    ) -> None:
        self.channel_path = channel_path
        self.archive_path = archive_path
        self.transcript_dir = transcript_dir
        self.quality = quality_engine or HeadingQualityEngine()
        self.resolver = resolver or CompositeHeadingResolver(
            quality_engine=self.quality,
        )

        self._channel_entries: dict[int, dict] = {}
        self._archive_entries: dict[int, dict] = {}
        self._load_metadata()

    def _load_metadata(self) -> None:
        if self.channel_path.exists():
            channel_data = json.loads(self.channel_path.read_text(encoding="utf-8"))
            for entry in channel_data.get("entries", []):
                num = parse_episode_number(entry.get("title", ""))
                if num is not None:
                    self._channel_entries[num] = entry

        if self.archive_path.exists():
            archive_data = json.loads(self.archive_path.read_text(encoding="utf-8"))
            for entry in archive_data:
                num = entry.get("number")
                if num is not None:
                    self._archive_entries[num] = entry

    @property
    def episode_numbers(self) -> list[int]:
        return sorted(set(self._channel_entries.keys()) & set(self._archive_entries.keys()))

    def get_metadata(self, number: int) -> EpisodeMetadata:
        channel_entry = self._channel_entries.get(number)
        archive_entry = self._archive_entries.get(number)
        if not channel_entry or not archive_entry:
            raise ValueError(f"Metadata not found for EP{number}")

        youtube_id = channel_entry["id"]
        youtube_url = f"https://www.youtube.com/watch?v={youtube_id}"
        duration_sec = round(channel_entry.get("duration") or 0)
        duration_str = format_duration(channel_entry.get("duration"))
        original_title = channel_entry.get("title") or f"EP{number}"
        display_title = archive_entry.get("display_title") or archive_entry.get("title") or original_title

        # Resolve episode date
        if archive_entry.get("date"):
            date, date_source = archive_entry["date"], "transcript_archive"
        else:
            meta_path = ROOT / ".work/samples" / f"{youtube_id}.metadata.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                raw = str(meta.get("upload_date") or "")
                if re.fullmatch(r"\d{8}", raw):
                    date = datetime.strptime(raw, "%Y%m%d").date().isoformat()
                    date_source = "youtube_metadata"
                else:
                    date, date_source = "未知", "unknown"
            else:
                date, date_source = "未知", "unknown"

        archive_filename = archive_entry.get("filename", f"EP{number}.md")
        archive_url = f"{ARCHIVE_BASE_URL}episode.html?file={quote(archive_filename)}"
        summary = archive_entry.get("summary", "").strip()

        return EpisodeMetadata(
            number=number,
            youtube_id=youtube_id,
            youtube_url=youtube_url,
            youtube_title=original_title,
            display_title=display_title,
            date=date,
            date_source=date_source,
            duration_str=duration_str,
            duration_seconds=duration_sec,
            archive_url=archive_url,
            summary=summary,
        )

    def load_transcript(self, number: int) -> str:
        path = self.transcript_dir / f"EP{number:04d}.md"
        if not path.exists():
            raise FileNotFoundError(f"Missing transcript for EP{number}: {path}")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def clean_transcript(text: str) -> str:
        # Strip leading sponsor section
        leading_separator = re.search(r"^\s*(?:\*{3,}|-{3,})\s*$", text, flags=re.M)
        if leading_separator and leading_separator.end() <= 5_000:
            leading_block = text[: leading_separator.start()]
            if re.search(r"(?:贊助|讚助|有贊助一個廣告|優惠碼|折扣碼|購物金)", leading_block):
                text = text[leading_separator.end() :]

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

        # Strip post-sponsor bridge
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

        # Strip trailing recap
        recap_patterns = (
            r"^\s*\(後續內容被截斷\)\s*$",
            r"^\s*\*\*本集重點回顧[：:]\*\*\s*$",
            r"^\s*#{1,3}\s*(?:本集)?(?:重點)?(?:回顧|總結)\s*$",
        )
        recap_positions = [m.start() for p in recap_patterns if (m := re.search(p, text, flags=re.M))]
        if recap_positions:
            text = text[: min(recap_positions)]

        text = re.sub(r"^#{1,6}\s+.*$", "", text, flags=re.M)
        text = re.sub(r"^\s*(?:-{3,}|\*{3,})\s*$", "", text, flags=re.M)
        text = re.sub(r"^\s*>\s?", "", text, flags=re.M)
        text = text.replace("**", "").replace("__", "")
        text = re.sub(r"https?://\S+", "", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def segment_sentences(text: str) -> list[str]:
        cleaned = EpisodeNoteSynthesizer.clean_transcript(text)
        return [s.strip() for s in re.split(r"(?<=[。！？!?])\s*", cleaned) if s.strip()]

    @staticmethod
    def make_chunks(text: str, target: int = 520) -> list[str]:
        result: list[str] = []
        current: list[str] = []
        size = 0
        for s in EpisodeNoteSynthesizer.segment_sentences(text):
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

    @staticmethod
    def features(text: str) -> Counter[str]:
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
        if not left or not right:
            return 0.0
        overlap = sum(min(weight, right.get(term, 0)) for term, weight in left.items())
        return overlap / max(1, sum(left.values()))

    @staticmethod
    def clean_excerpt(text: str) -> str:
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
        if len(text) > MAX_EXCERPT_CHARS:
            clauses = re.split(r"(?<=[，；;：:])", text)
            kept = ""
            for clause in clauses:
                if len(kept) + len(clause) > MAX_EXCERPT_CHARS - 1:
                    break
                kept += clause
            if kept:
                return kept.rstrip("，；;：:。！？!?") + "…"
            return text[: MAX_EXCERPT_CHARS - 1].rstrip("，；;：:。！？!?") + "…"
        return text.rstrip("。！？!?；;") + terminal

    def extract_evidence(self, number: int) -> list[dict]:
        """Extract structured chapter evidence directly from transcript and summary without parsing Markdown."""
        meta = self.get_metadata(number)
        transcript = self.load_transcript(number)
        return self._extract_evidence_from_raw(meta.summary, transcript)

    def _extract_evidence_from_raw(self, summary: str, transcript: str) -> list[dict]:
        chunks = self.make_chunks(transcript)
        if not chunks:
            raise ValueError("Empty transcript")
        chunk_features = [self.features(chunk) for chunk in chunks]
        seeds = self.split_seeds(summary)
        assignments: list[tuple[int, str, list[tuple[float, int]]]] = []
        used_anchors: set[int] = set()

        for seed_index, seed in enumerate(seeds):
            seed_features = self.features(seed)
            expected_pos = (seed_index + 0.5) / len(seeds)
            ranked = []
            for idx, chunk in enumerate(chunks):
                score = self.similarity(seed_features, chunk_features[idx])
                score -= 0.07 * abs(idx / max(1, len(chunks) - 1) - expected_pos)
                if any(m in chunk for m in SPONSOR_MARKERS):
                    score -= 0.25
                ranked.append((score, idx))
            ranked.sort(reverse=True)
            anchor = next((idx for _, idx in ranked if idx not in used_anchors), ranked[0][1])
            used_anchors.add(anchor)
            assignments.append((anchor, seed, ranked[:8]))

        assignments.sort(key=lambda item: item[0])
        chapters: list[dict] = []
        used_excerpts: set[str] = set()
        normalized_summary = re.sub(r"\s+", "", summary)

        for anchor, seed, ranked_chunks in assignments:
            seed_features = self.features(seed)
            candidate_indices = set()
            for _, chunk_idx in ranked_chunks[:5]:
                candidate_indices.update(
                    idx
                    for idx in (chunk_idx - 1, chunk_idx, chunk_idx + 1)
                    if 0 <= idx < len(chunks)
                )
            candidate_sentences: list[tuple[float, int, str]] = []
            for chunk_idx in sorted(candidate_indices):
                for sentence in self.segment_sentences(chunks[chunk_idx]):
                    if not 24 <= len(sentence) <= 300 or any(m in sentence for m in SPONSOR_MARKERS):
                        continue
                    score = self.similarity(seed_features, self.features(sentence))
                    if sentence.endswith(("？", "?")):
                        score -= 0.04
                    candidate_sentences.append((score, chunk_idx, sentence))
            candidate_sentences.sort(reverse=True)

            excerpts: list[str] = []
            for _, chunk_idx, sentence in candidate_sentences:
                excerpt = self.clean_excerpt(sentence)
                normalized = re.sub(r"\s+", "", excerpt.rstrip("。"))
                if normalized in normalized_summary or normalized in used_excerpts:
                    continue
                if any(normalized in existing or existing in normalized for existing in used_excerpts):
                    continue
                excerpts.append(excerpt)
                used_excerpts.add(normalized)
                if len(excerpts) == 2:
                    break

            if len(excerpts) < 2:
                # Fallback to candidate sentences if strict uniqueness exhausted
                for _, _, sentence in candidate_sentences:
                    excerpt = self.clean_excerpt(sentence)
                    if excerpt not in excerpts:
                        excerpts.append(excerpt)
                    if len(excerpts) == 2:
                        break

            if len(excerpts) < 2:
                raise ValueError(f"Could not extract two distinct points for seed: {seed}")

            # Position in transcript
            pos = min(
                self.clean_transcript(transcript).lower().find(self.quality.compact(e))
                for e in excerpts
            )
            chapters.append({
                "position": pos,
                "title": seed,
                "excerpts": tuple(excerpts),
            })

        return sorted(chapters, key=lambda ch: ch["position"])

    def synthesize_episode(
        self,
        number: int,
        resolver: HeadingResolver | None = None,
    ) -> EpisodeNote:
        """Synthesize a complete EpisodeNote domain entity."""
        meta = self.get_metadata(number)
        raw_chapters = self.extract_evidence(number)
        active_resolver = resolver or self.resolver
        headings = active_resolver.resolve(meta, raw_chapters)

        chapters: list[Chapter] = []
        for idx, (raw, heading) in enumerate(zip(raw_chapters, headings, strict=True), 1):
            chapters.append(
                Chapter(
                    index=idx,
                    heading=heading,
                    excerpts=tuple(raw["excerpts"]),
                    position=raw["position"],
                )
            )

        return EpisodeNote(metadata=meta, chapters=tuple(chapters))

    def synthesize_all(
        self,
        output_dir: Path = OUTPUT_DIR,
        resolver: HeadingResolver | None = None,
    ) -> SynthesisSummary:
        """Batch synthesize all episode notes, write markdown files, index, and readme."""
        episodes_dir = output_dir / "episodes"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        episodes_dir.mkdir(parents=True, exist_ok=True)

        notes: list[EpisodeNote] = []
        chapter_counts: Counter[int] = Counter()
        total_seconds = 0

        for number in self.episode_numbers:
            note = self.synthesize_episode(number, resolver=resolver)
            (episodes_dir / f"EP{number:04d}.md").write_text(note.render_markdown(), encoding="utf-8")
            notes.append(note)
            chapter_counts[len(note.chapters)] += 1
            total_seconds += note.metadata.duration_seconds

        total_chapters = sum(len(note.chapters) for note in notes)
        summary = SynthesisSummary(
            total_episodes=len(notes),
            total_chapters=total_chapters,
            total_seconds=total_seconds,
            chapter_distribution=chapter_counts,
            notes=tuple(notes),
        )

        (output_dir / "README.md").write_text(self.render_readme(notes, summary), encoding="utf-8")
        (output_dir / "_index.md").write_text(self.render_index(notes, summary), encoding="utf-8")

        return summary

    @staticmethod
    def render_readme(notes: Sequence[EpisodeNote], summary: SynthesisSummary) -> str:
        hours = summary.total_seconds / 3600
        years = sorted({note.metadata.date[:4] for note in notes if re.match(r"\d{4}-", note.metadata.date)})
        dist_str = "、".join(f"{count} 章：{episodes} 集" for count, episodes in sorted(summary.chapter_distribution.items()))
        return f"""# Gooaye 股癌 YouTube 全集章節觀念整理

本資料夾收錄 **{len(notes)} 支目前公開的 YouTube 影片**，涵蓋 EP1–EP690（YouTube 公開清單沒有 EP232），合計約 **{hours:.1f} 小時**。全集共 **{summary.total_chapters:,} 章**、**{2 * summary.total_chapters:,} 條逐字稿摘錄**；每集各有一份 Markdown，以完整逐字稿為內容依據，整理成依討論順序排列的章節觀念。

- [全集索引](_index.md)
- [逐集筆記](episodes/)
- 頻道：[{CHANNEL_URL}]({CHANNEL_URL})
- 年份範圍：{years[0]}–{years[-1]}
- 章節分布：{dist_str}

## 檔案格式

每份 `episodes/EPxxxx.md` 包含 YAML metadata、YouTube 原始資訊、3–6 個觀念章節，以及來源與方法說明。每章兩個條列均取自完整逐字稿中的相關段落，並限制為短篇摘錄，方便回查原音。頁首使用的 `display_title`／策展標題來自第三方逐字稿索引，YouTube 原始標題則獨立保留於 metadata 與內文。

## 整理方式與限制

- YouTube 頻道沒有可用的手動或自動字幕；本資料使用公開非官方逐字稿網站提供的**完整逐字稿**。該站說明內容由 AI 聽寫並經人工修正。
- 第三方 `summary` 欄位只用來搜尋全文中的候選主題，**沒有原文複製成「本集摘要」**；實際章節條列來自完整逐字稿，而非把摘要按標點拆段。
- 各章標題由該章入選的兩段完整逐字稿摘錄重新命名：命名模型的輸入不含第三方 `summary`；`summary` 只在產生後用來拒絕撞句，少數未通過自動驗證者由人工直接依兩段摘錄覆核。章序依入選摘錄在逐字稿中的實際位置排列。
- 這些章節是主題／觀念索引，不是精確時間碼。
- 日期主要來自第三方逐字稿索引，不宣稱已逐集核對 YouTube 上傳日期；唯一缺日期的 EP162 使用單支 YouTube metadata 補為 2021-07-31。
- 公開 YouTube 清單共有 {len(notes)} 支，集數缺 EP232；只收錄實際出現在頻道公開清單中的影片。
- 非官方逐字稿與抽取結果可能有聽寫或專有名詞錯誤，正確內容以原始影片為準。
- 所有內容僅供學習與索引，不構成投資建議。

產生日期：{datetime.now().date().isoformat()}
"""

    @staticmethod
    def render_index(notes: Sequence[EpisodeNote], summary: SynthesisSummary) -> str:
        grouped: dict[str, list[EpisodeNote]] = defaultdict(list)
        for note in sorted(notes, key=lambda n: n.metadata.number, reverse=True):
            year = note.metadata.date[:4] if re.match(r"\d{4}-", note.metadata.date) else "日期未知"
            grouped[year].append(note)

        lines = [
            "# 全集索引",
            "",
            f"共 {len(notes)} 支 YouTube 公開影片、{summary.total_chapters:,} 章、{2 * summary.total_chapters:,} 條逐字稿摘錄；涵蓋 EP1–EP690，公開清單唯一缺號為 EP232。章節按完整逐字稿內容順序編排，非精確時間碼。",
            "",
            "| 年份 | 集數 |",
            "|---:|---:|",
        ]
        for year in sorted(grouped, reverse=True):
            lines.append(f"| {year} | {len(grouped[year])} |")

        for year in sorted(grouped, reverse=True):
            lines.extend(["", f"## {year}", "", "| 集數 | 日期 | 片長 | 章節 | 標題 | YouTube |", "|---:|:---:|---:|---:|---|:---:|"])
            for note in grouped[year]:
                title = note.metadata.display_title.replace("|", "\\|").replace("\n", " ")
                lines.append(
                    f"| [EP{note.metadata.number}](episodes/EP{note.metadata.number:04d}.md) | "
                    f"{note.metadata.date} | {note.metadata.duration_str} | {len(note.chapters)} | {title} | "
                    f"[觀看]({note.metadata.youtube_url}) |"
                )
        lines.append("")
        return "\n".join(lines)


if __name__ == "__main__":
    synthesizer = EpisodeNoteSynthesizer()
    print(f"Discovered {len(synthesizer.episode_numbers)} episodes ready for synthesis.")
