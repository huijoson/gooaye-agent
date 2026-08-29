#!/usr/bin/env python3
"""Episode Note Synthesizer - Deep module orchestrating transcript processing, evidence extraction, heading resolution, and Markdown synthesis."""

from __future__ import annotations

import concurrent.futures
import logging
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Sequence

# Domain models
from domain import (
    Chapter,
    ChapterEvidence,
    EpisodeMetadata,
    EpisodeNote,
    SynthesisSummary,
    DefectCategory,
    Defect,
    QualityReport,
    yaml_string,
)

# Deep modules
from heading_quality_engine import HeadingQualityEngine
from transcript_processor import (
    TranscriptSanitizer,
    TranscriptSegmenter,
    TranscriptFeatureExtractor,
    MAX_EXCERPT_CHARS,
    SPONSOR_MARKERS,
)
from evidence_extractor import EvidenceExtractor
from heading_resolver import (
    HeadingResolver,
    CachedHeadingResolver,
    DeterministicHeadingResolver,
    CompositeHeadingResolver,
    OllamaHeadingResolver,
)
from takeaway_quality_engine import TakeawayQualityEngine
from takeaway_resolver import (
    TakeawayResolver,
    CachedTakeawayResolver,
    DeterministicTakeawayResolver,
    CompositeTakeawayResolver,
)
from markdown_renderer import MarkdownRenderer
from episode_source_repository import EpisodeSourceRepository

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CHANNEL_PATH = ROOT / ".work/channel.json"
ARCHIVE_PATH = ROOT / ".work/source/episodes.json"
TRANSCRIPT_DIR = ROOT / ".work/full-transcripts"
SNAPSHOT_ROOT = ROOT / ".work/episode-sources"
HEADINGS_CACHE_DIR = ROOT / ".work/grounded-headings"
OUTPUT_DIR = ROOT / "gooaye-youtube-notes"
EPISODES_DIR = OUTPUT_DIR / "episodes"
CHANNEL_URL = "https://www.youtube.com/@Gooaye/videos"
ARCHIVE_BASE_URL = "https://whatmkreallysaid.com/"


def parse_episode_number(title: str) -> int | None:
    """Extract integer episode number from EP prefix."""
    match = re.search(r"\bEP\s*(\d+)\b", title, re.IGNORECASE)
    return int(match.group(1)) if match else None


class EpisodeNoteSynthesizer:
    """Deep module orchestrating transcript cleaning, evidence extraction, heading resolution, and Markdown note synthesis."""

    def __init__(
        self,
        channel_path: Path = CHANNEL_PATH,
        archive_path: Path = ARCHIVE_PATH,
        transcript_dir: Path = TRANSCRIPT_DIR,
        cache_dir: Path = HEADINGS_CACHE_DIR,
        resolver: HeadingResolver | None = None,
        takeaway_resolver: TakeawayResolver | None = None,
        quality_engine: HeadingQualityEngine | None = None,
        takeaway_quality_engine: TakeawayQualityEngine | None = None,
        sanitizer: TranscriptSanitizer | None = None,
        segmenter: TranscriptSegmenter | None = None,
        feature_extractor: TranscriptFeatureExtractor | None = None,
        evidence_extractor: EvidenceExtractor | None = None,
        renderer: MarkdownRenderer | None = None,
        source_repository: EpisodeSourceRepository | None = None,
    ) -> None:
        self.channel_path = channel_path
        self.archive_path = archive_path
        self.transcript_dir = transcript_dir
        self.cache_dir = cache_dir
        self.source_repository = source_repository or EpisodeSourceRepository(
            snapshot_root=channel_path.parent / "episode-sources",
            legacy_channel_path=channel_path,
            legacy_archive_path=archive_path,
            legacy_transcript_dir=transcript_dir,
            archive_base_url=ARCHIVE_BASE_URL,
        )

        self.quality = quality_engine or HeadingQualityEngine()
        self.takeaway_quality = takeaway_quality_engine or TakeawayQualityEngine()
        self.sanitizer = sanitizer or TranscriptSanitizer()
        self.segmenter = segmenter or TranscriptSegmenter(sanitizer=self.sanitizer)
        self.features_extractor = feature_extractor or TranscriptFeatureExtractor()
        self.evidence_extractor = evidence_extractor or EvidenceExtractor(
            sanitizer=self.sanitizer,
            segmenter=self.segmenter,
            feature_extractor=self.features_extractor,
        )
        self.renderer = renderer or MarkdownRenderer()

        self.resolver = resolver or CompositeHeadingResolver(
            cache_dir=self.cache_dir,
            quality_engine=self.quality,
        )
        self.takeaway_resolver = takeaway_resolver or CompositeTakeawayResolver(
            primary=CachedTakeawayResolver(cache_dir=self.cache_dir, quality_engine=self.takeaway_quality),
            secondary=DeterministicTakeawayResolver(quality_engine=self.takeaway_quality),
            quality_engine=self.takeaway_quality,
        )

    @property
    def episode_numbers(self) -> list[int]:
        """List all episodes available through the episode source boundary."""
        return self.source_repository.episode_numbers

    def get_metadata(self, number: int) -> EpisodeMetadata:
        """Retrieve unified metadata through the episode source boundary."""
        return self.source_repository.get_metadata(number)

    def load_transcript(self, number: int) -> str:
        """Load raw full transcript text through the episode source boundary."""
        return self.source_repository.load_transcript(number)

    # Static delegations for backward compatibility
    @staticmethod
    def clean_transcript(text: str) -> str:
        return TranscriptSanitizer.clean(text)

    @staticmethod
    def segment_sentences(text: str) -> list[str]:
        return TranscriptSegmenter().segment_sentences(text)

    @staticmethod
    def make_chunks(text: str, target: int = 520) -> list[str]:
        return TranscriptSegmenter().make_chunks(text, target=target)

    @staticmethod
    def split_seeds(summary: str) -> list[str]:
        return TranscriptSegmenter.split_seeds(summary)

    @staticmethod
    def features(text: str) -> Counter[str]:
        return TranscriptFeatureExtractor.features(text)

    @staticmethod
    def similarity(left: Counter[str], right: Counter[str]) -> float:
        return TranscriptFeatureExtractor.similarity(left, right)

    @staticmethod
    def clean_excerpt(text: str) -> str:
        return TranscriptSanitizer.clean_excerpt(text)

    @staticmethod
    def render_readme(notes: Sequence[EpisodeNote], summary: SynthesisSummary) -> str:
        return MarkdownRenderer.render_readme(notes, summary)

    @staticmethod
    def render_index(notes: Sequence[EpisodeNote], summary: SynthesisSummary) -> str:
        return MarkdownRenderer.render_index(notes, summary)

    def _extract_evidence_from_raw(self, summary: str, transcript: str) -> list[ChapterEvidence]:
        """Extract evidence from raw summary and transcript strings."""
        return self.evidence_extractor.extract(transcript, summary=summary)

    def extract_evidence(self, number: int) -> list[ChapterEvidence]:
        """Extract structured chapter evidence directly from transcript and summary without parsing Markdown."""
        meta = self.get_metadata(number)
        transcript = self.load_transcript(number)
        return self._extract_evidence_from_raw(meta.summary, transcript)

    def synthesize_episode(
        self,
        number: int,
        resolver: HeadingResolver | None = None,
        takeaway_resolver: TakeawayResolver | None = None,
    ) -> EpisodeNote:
        """Synthesize a complete EpisodeNote domain entity with headings and takeaways."""
        meta = self.get_metadata(number)
        raw_chapters = self.extract_evidence(number)
        active_resolver = resolver or self.resolver
        active_takeaway_resolver = takeaway_resolver or self.takeaway_resolver

        headings = active_resolver.resolve(meta, raw_chapters)
        takeaways = active_takeaway_resolver.resolve(meta, raw_chapters)

        chapters: list[Chapter] = []
        for idx, (raw, heading, takeaway) in enumerate(
            zip(raw_chapters, headings, takeaways, strict=True), 1
        ):
            chapters.append(
                Chapter(
                    index=idx,
                    heading=heading,
                    takeaway=takeaway,
                    excerpts=raw.excerpts if isinstance(raw, ChapterEvidence) else tuple(raw["excerpts"]),
                    position=raw.position if isinstance(raw, ChapterEvidence) else raw.get("position", 0),
                )
            )

        return EpisodeNote(metadata=meta, chapters=tuple(chapters))

    def synthesize_all(
        self,
        output_dir: Path = OUTPUT_DIR,
        resolver: HeadingResolver | None = None,
        takeaway_resolver: TakeawayResolver | None = None,
        max_workers: int = 1,
        episode_numbers: Sequence[int] | None = None,
    ) -> SynthesisSummary:
        """Batch synthesize all episode notes, write markdown files (slim and full), index, and readme."""
        episodes_dir = output_dir / "episodes"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        episodes_dir.mkdir(parents=True, exist_ok=True)

        active_resolver = resolver or self.resolver
        active_takeaway_resolver = takeaway_resolver or self.takeaway_resolver
        target_numbers = list(episode_numbers) if episode_numbers is not None else self.episode_numbers

        def _process(number: int) -> EpisodeNote:
            note = self.synthesize_episode(
                number,
                resolver=active_resolver,
                takeaway_resolver=active_takeaway_resolver,
            )
            (episodes_dir / f"EP{number:04d}.md").write_text(
                note.render_markdown(mode="slim"),
                encoding="utf-8",
            )
            (episodes_dir / f"EP{number:04d}.full.md").write_text(
                note.render_markdown(mode="full"),
                encoding="utf-8",
            )
            return note

        if max_workers > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                notes = list(executor.map(_process, target_numbers))
        else:
            notes = [_process(number) for number in target_numbers]

        chapter_counts: Counter[int] = Counter()
        total_seconds = 0
        for note in notes:
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

        (output_dir / "README.md").write_text(self.renderer.render_readme(notes, summary), encoding="utf-8")
        (output_dir / "_index.md").write_text(self.renderer.render_index(notes, summary), encoding="utf-8")

        return summary

    def audit(
        self,
        resolver: HeadingResolver | None = None,
        takeaway_resolver: TakeawayResolver | None = None,
        episode_numbers: Sequence[int] | None = None,
    ) -> dict[str, int | list[dict]]:
        """Audit all episodes in the corpus and report any heading or takeaway defects."""
        active_resolver = resolver or self.resolver
        active_takeaway_resolver = takeaway_resolver or self.takeaway_resolver
        target_numbers = list(episode_numbers) if episode_numbers is not None else self.episode_numbers

        total_chapters = 0
        defects_found: list[dict] = []

        for number in target_numbers:
            try:
                meta = self.get_metadata(number)
                raw_chapters = self.extract_evidence(number)
                headings = active_resolver.resolve(meta, raw_chapters)
                takeaways = active_takeaway_resolver.resolve(meta, raw_chapters)

                for idx, (h, t, ch) in enumerate(zip(headings, takeaways, raw_chapters), 1):
                    total_chapters += 1
                    excerpts = ch.excerpts if isinstance(ch, ChapterEvidence) else tuple(ch["excerpts"])
                    h_report = self.quality.diagnose(h, excerpts, meta.summary)
                    t_report = self.takeaway_quality.diagnose(t, excerpts)

                    chapter_defects = []
                    if not h_report.is_valid:
                        chapter_defects.extend([f"Heading: {d.message}" for d in h_report.defects])
                    if not t_report.is_valid:
                        chapter_defects.extend([f"Takeaway: {d.message}" for d in t_report.defects])

                    if chapter_defects:
                        defects_found.append({
                            "episode": number,
                            "chapter": idx,
                            "heading": h,
                            "takeaway": t,
                            "defects": chapter_defects,
                        })
            except Exception as e:
                defects_found.append({
                    "episode": number,
                    "error": str(e),
                })

        return {
            "total_episodes": len(target_numbers),
            "total_chapters": total_chapters,
            "defects_count": len(defects_found),
            "defects": defects_found,
        }


if __name__ == "__main__":
    synthesizer = EpisodeNoteSynthesizer()
    print(f"Discovered {len(synthesizer.episode_numbers)} episodes ready for synthesis.")
