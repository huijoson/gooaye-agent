"""Domain models and entities for the Gooaye note synthesis system."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence


def yaml_string(value: str) -> str:
    """Format string for YAML frontmatter escaping."""
    return json.dumps(value, ensure_ascii=False)


def format_duration(seconds: int | float | None) -> str:
    """Format seconds into MM:SS or HH:MM:SS."""
    if seconds is None:
        return "未知"
    seconds = round(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


class DefectCategory(str, Enum):
    """Categories of defects in chapter headings."""
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
    """Represents a specific flaw detected in a heading."""
    category: DefectCategory
    message: str
    trigger: str = ""


@dataclass(frozen=True)
class QualityReport:
    """Diagnostic report produced by HeadingQualityEngine."""
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


@dataclass(frozen=True)
class ChapterEvidence:
    """In-memory evidence anchored from full transcript for a single chapter."""
    index: int
    seed_title: str
    excerpts: tuple[str, ...]
    position: int = 0

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "title": self.seed_title,
            "excerpts": self.excerpts,
            "position": self.position,
        }

    @classmethod
    def from_dict(cls, data: dict, default_index: int = 1) -> ChapterEvidence:
        return cls(
            index=data.get("index", default_index),
            seed_title=data.get("title") or data.get("seed_title", ""),
            excerpts=tuple(data.get("excerpts", ())),
            position=data.get("position", 0),
        )


@dataclass(frozen=True)
class Chapter:
    """Domain representation of a structured concept chapter."""
    index: int
    heading: str
    takeaway: str = ""
    excerpts: tuple[str, ...] = ()
    position: int = 0


@dataclass(frozen=True)
class EpisodeMetadata:
    """Domain representation of episode metadata."""
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
    transcription: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EpisodeSourceSnapshot:
    """A complete, synthesis-ready set of source data for one episode."""
    number: int
    youtube_id: str
    youtube_title: str
    published_at: str
    duration_seconds: int
    archive_filename: str
    display_title: str
    archive_date: str
    summary: str
    transcript: str
    source_urls: Mapping[str, str]
    fetched_at: str
    transcription: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EpisodeSourceVerification:
    """Integrity result for a persisted episode source snapshot."""
    number: int
    defects: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        return not self.defects


@dataclass(frozen=True)
class EpisodeNote:
    """Domain representation of a complete episode note."""
    metadata: EpisodeMetadata
    chapters: tuple[Chapter, ...]

    def render_markdown(self, mode: str = "slim") -> str:
        chapter_markdown = []
        for ch in self.chapters:
            lines = []
            if ch.takeaway:
                lines.append(f"- **核心觀點：** {ch.takeaway}")
            
            excerpts = ch.excerpts[:2] if mode == "slim" else ch.excerpts
            for bullet in excerpts:
                lines.append(f"- {bullet}")

            body = "\n".join(lines)
            chapter_markdown.append(f"### {ch.index}. {ch.heading}\n\n{body}")

        source_description = self._source_description()
        asr_frontmatter = ""
        if self.metadata.transcription:
            asr_frontmatter = "source: \"official_audio_asr\"\n" + "".join(
                f"transcription_{key}: {yaml_string(value)}\n"
                for key, value in sorted(self.metadata.transcription.items())
            )
        return f"""---
episode: {self.metadata.number}
title: {yaml_string(self.metadata.display_title)}
youtube_title: {yaml_string(self.metadata.youtube_title)}
youtube_id: {yaml_string(self.metadata.youtube_id)}
youtube_url: {yaml_string(self.metadata.youtube_url)}
episode_date: {yaml_string(self.metadata.date)}
episode_date_source: {yaml_string(self.metadata.date_source)}
duration: {yaml_string(self.metadata.duration_str)}
content_method: {yaml_string("hybrid_extractive_distilled")}
{asr_frontmatter}---

# EP{self.metadata.number}｜{self.metadata.display_title}

- **YouTube 原始標題：** {self.metadata.youtube_title}
- **節目日期：** {self.metadata.date}
- **片長：** {self.metadata.duration_str}
- **影片：** [YouTube]({self.metadata.youtube_url})

## 章節觀念

{chr(10).join(chr(10) + ch for ch in chapter_markdown)}

## 資料來源與整理方式

- 影片資訊：[Gooaye 股癌 YouTube]({self.metadata.youtube_url})
{source_description}
- 本文僅供學習與索引，不構成投資建議。
"""

    def _source_description(self) -> str:
        if self.metadata.transcription:
            details = self.metadata.transcription
            return (
                f"- 完整內容依據：[官方節目音訊]({details['audio_url']}) 的自動語音轉錄。\n"
                f"- 轉錄引擎：{details['engine']}；模型：{details['model']}。\n"
                "- 頁首標題與節目日期來自官方節目 metadata；沒有使用第三方策展摘要。\n"
                "- 章節與條列依自動轉錄文字抽取；未經逐句人工校對，專有名詞或數字可能辨識錯誤，請以原始音訊為準。"
            )
        return f"""- 完整內容依據：[公開非官方逐字稿]({self.metadata.archive_url})
- 頁首策展標題來自第三方逐字稿索引；YouTube 原始標題另列於上方。
- 第三方摘要只作全文檢索提示；章節按入選摘錄在**完整逐字稿**中的實際位置排序。命名模型只接收每章全文摘錄，不接收摘要；摘要只在事後用來拒絕撞句，少數未通過自動驗證的標題由人工直接依摘錄覆核。條列也是全文短摘錄，而非摘要切片。
- 節目日期主要取自第三方逐字稿索引；若該欄缺漏，才使用單支 YouTube metadata。日期不宣稱等同 YouTube 上傳日。
- 本文沒有虛構時間碼。非官方逐字稿可能有聽寫或專有名詞錯誤，請以原始影片為準。"""


@dataclass(frozen=True)
class SynthesisSummary:
    """Summary statistics for batch note synthesis."""
    total_episodes: int
    total_chapters: int
    total_seconds: int
    chapter_distribution: Counter[int]
    notes: tuple[EpisodeNote, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TopicDefinition:
    """Definition and keyword metadata for a thematic guide."""
    slug: str
    title: str
    description: str
    category: str
    keywords: tuple[str, ...] = field(default_factory=tuple)
    core_concepts: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ThematicChapterRef:
    """A chapter reference matched and ranked for a thematic guide."""
    episode_number: int
    episode_title: str
    published_at: str
    chapter_index: int
    heading: str
    takeaway: str
    relevance_score: float
    matched_keywords: tuple[str, ...] = field(default_factory=tuple)
    excerpts: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ThematicMilestone:
    """A historical inflection point or milestone in the topic evolution."""
    period: str
    summary: str
    key_episodes: tuple[int, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TopicGuide:
    """Domain representation of a synthesized thematic knowledge guide."""
    definition: TopicDefinition
    time_span: tuple[str, str]
    summary_takeaways: tuple[str, ...] = field(default_factory=tuple)
    milestones: tuple[ThematicMilestone, ...] = field(default_factory=tuple)
    chapters: tuple[ThematicChapterRef, ...] = field(default_factory=tuple)
    faq: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def slug(self) -> str:
        return self.definition.slug

    @property
    def title(self) -> str:
        return self.definition.title

    @property
    def category(self) -> str:
        return self.definition.category

    @property
    def description(self) -> str:
        return self.definition.description

    @property
    def episodes_count(self) -> int:
        return len({ch.episode_number for ch in self.chapters})

    @property
    def chapters_count(self) -> int:
        return len(self.chapters)
