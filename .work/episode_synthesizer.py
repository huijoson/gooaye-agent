#!/usr/bin/env python3
"""Episode Note Synthesizer - Deep module orchestrating transcript processing, evidence extraction, heading resolution, and Markdown synthesis."""

from __future__ import annotations

import concurrent.futures
import logging
import re
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
CHANNEL_URL = "https://www.youtube.com/@Gooaye/videos"
ARCHIVE_BASE_URL = "https://whatmkreallysaid.com/"


class PreviewOutputError(ValueError):
    """A compatibility writer was not given an isolated Preview destination."""


def validate_preview_output_directory(output_dir: Path | None) -> Path:
    """Reject implicit, formal, and broad destinations before any Preview write."""
    if output_dir is None:
        raise PreviewOutputError("Preview output directory must be provided explicitly.")
    destination = Path(output_dir)
    if destination.is_symlink():
        raise PreviewOutputError("Preview output directory must not be a symlink.")
    resolved = destination.resolve(strict=False)
    formal_root = OUTPUT_DIR.resolve(strict=False)
    try:
        resolved.relative_to(formal_root)
    except ValueError:
        pass
    else:
        raise PreviewOutputError(
            "Preview output directory must not be the formal publication root or a descendant."
        )
    protected = {
        Path(resolved.anchor),
        Path.home().resolve(),
        ROOT.resolve(),
    }
    if resolved in protected:
        raise PreviewOutputError("Preview output directory is a protected broad destination.")
    if destination.exists() and not destination.is_dir():
        raise PreviewOutputError("Preview output directory must be a directory.")
    if destination.exists() and any(destination.iterdir()):
        raise PreviewOutputError("Preview output directory must be new or empty.")
    return destination


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

    @staticmethod
    def _prepare_asr_transcript(transcript: str, meta: EpisodeMetadata) -> str:
        """Bound unpunctuated ASR passages for extraction, preserving stored text.

        Line boundaries come from ASR segments. Punctuation added here is an
        extraction boundary, not a claim about exact spoken sentence structure.
        An explicitly reviewed one-based content_start_line can exclude intro ads.
        """
        lines = transcript.splitlines()
        start = meta.transcription.get("content_start_line")
        if start is not None:
            try:
                line_number = int(start)
            except (TypeError, ValueError) as exc:
                raise ValueError("ASR content_start_line must be a one-based line number") from exc
            if not 1 <= line_number <= len(lines):
                raise ValueError("ASR content_start_line is outside the transcript")
            lines = lines[line_number - 1:]

        paragraphs: list[str] = []
        pending = ""

        def flush() -> None:
            nonlocal pending
            if pending:
                paragraphs.append(pending if pending[-1] in "。！？!?" else pending + "。")
                pending = ""

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                flush()
                continue
            if re.fullmatch(r"(?:-{3,}|\*{3,})", line):
                flush()
                paragraphs.append(line)
                continue
            # Preserve existing sentence punctuation; split very long ASR
            # segments only when no natural sentence boundary was emitted.
            for sentence in re.split(r"(?<=[。！？!?])", line):
                sentence = sentence.strip()
                for offset in range(0, len(sentence), 140):
                    fragment = sentence[offset:offset + 140]
                    if pending and len(pending) + len(fragment) + 1 > 140:
                        flush()
                    pending = f"{pending} {fragment}" if pending else fragment
                    if pending[-1] in "。！？!?" or len(pending) >= 100:
                        flush()
        flush()
        return "\n".join(paragraphs)

    def extract_evidence(self, number: int) -> list[ChapterEvidence]:
        """Extract structured chapter evidence directly from transcript and summary without parsing Markdown."""
        meta = self.get_metadata(number)
        transcript = self.load_transcript(number)
        if meta.transcription:
            transcript = self._prepare_asr_transcript(transcript, meta)
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
        output_dir: Path | None = None,
        resolver: HeadingResolver | None = None,
        takeaway_resolver: TakeawayResolver | None = None,
        max_workers: int = 1,
        episode_numbers: Sequence[int] | None = None,
    ) -> SynthesisSummary:
        """Write an isolated Preview of episode notes without publication-level indexes."""
        output_dir = validate_preview_output_directory(output_dir)
        summary = self.synthesize_notes(
            resolver=resolver,
            takeaway_resolver=takeaway_resolver,
            max_workers=max_workers,
            episode_numbers=episode_numbers,
        )

        episodes_dir = output_dir / "episodes"
        episodes_dir.mkdir(parents=True, exist_ok=True)

        for note in summary.notes:
            number = note.metadata.number
            (episodes_dir / f"EP{number:04d}.md").write_text(
                note.render_markdown(mode="slim"),
                encoding="utf-8",
            )
            (episodes_dir / f"EP{number:04d}.full.md").write_text(
                note.render_markdown(mode="full"),
                encoding="utf-8",
            )

        return summary

    def synthesize_notes(
        self,
        resolver: HeadingResolver | None = None,
        takeaway_resolver: TakeawayResolver | None = None,
        max_workers: int = 1,
        episode_numbers: Sequence[int] | None = None,
    ) -> SynthesisSummary:
        """Batch synthesize EpisodeNotes in memory without writing publication files."""
        active_resolver = resolver or self.resolver
        active_takeaway_resolver = takeaway_resolver or self.takeaway_resolver
        target_numbers = list(episode_numbers) if episode_numbers is not None else self.episode_numbers

        def _process(number: int) -> EpisodeNote:
            return self.synthesize_episode(
                number,
                resolver=active_resolver,
                takeaway_resolver=active_takeaway_resolver,
            )

        if max_workers > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                notes = list(executor.map(_process, target_numbers))
        else:
            notes = [_process(number) for number in target_numbers]

        chapter_counts: Counter[int] = Counter(len(note.chapters) for note in notes)
        return SynthesisSummary(
            total_episodes=len(notes),
            total_chapters=sum(len(note.chapters) for note in notes),
            total_seconds=sum(note.metadata.duration_seconds for note in notes),
            chapter_distribution=chapter_counts,
            notes=tuple(notes),
        )

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
