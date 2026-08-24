"""Evidence extractor - Anchors grounded transcript excerpts to topic seeds."""

from __future__ import annotations

import re
from typing import Sequence

from domain import ChapterEvidence
from transcript_processor import (
    TranscriptSanitizer,
    TranscriptSegmenter,
    TranscriptFeatureExtractor,
    SPONSOR_MARKERS,
)


class EvidenceExtractor:
    """Extract grounded chapter evidence tuples from full transcripts and curated summaries."""

    def __init__(
        self,
        sanitizer: TranscriptSanitizer | None = None,
        segmenter: TranscriptSegmenter | None = None,
        feature_extractor: TranscriptFeatureExtractor | None = None,
    ) -> None:
        self.sanitizer = sanitizer or TranscriptSanitizer()
        self.segmenter = segmenter or TranscriptSegmenter(sanitizer=self.sanitizer)
        self.features = feature_extractor or TranscriptFeatureExtractor()

    def extract(self, summary: str, transcript: str) -> list[ChapterEvidence]:
        """Extract structured chapter evidence directly from transcript and summary."""
        chunks = self.segmenter.make_chunks(transcript)
        if not chunks:
            raise ValueError("Empty transcript")

        chunk_features = [self.features.features(chunk) for chunk in chunks]
        seeds = self.segmenter.split_seeds(summary)
        assignments: list[tuple[int, str, list[tuple[float, int]]]] = []
        used_anchors: set[int] = set()

        for seed_index, seed in enumerate(seeds):
            seed_features = self.features.features(seed)
            expected_pos = (seed_index + 0.5) / len(seeds)
            ranked = []
            for idx, chunk in enumerate(chunks):
                score = self.features.similarity(seed_features, chunk_features[idx])
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
        cleaned_transcript = self.sanitizer.clean(transcript)
        cleaned_transcript_compact = re.sub(r"[\s\W_]+", "", cleaned_transcript.lower())

        for anchor, seed, ranked_chunks in assignments:
            seed_features = self.features.features(seed)
            candidate_indices = set()
            for _, chunk_idx in ranked_chunks[:5]:
                candidate_indices.update(
                    idx
                    for idx in (chunk_idx - 1, chunk_idx, chunk_idx + 1)
                    if 0 <= idx < len(chunks)
                )
            candidate_sentences: list[tuple[float, int, str]] = []
            for chunk_idx in sorted(candidate_indices):
                for sentence in self.segmenter.segment_sentences(chunks[chunk_idx]):
                    if not 24 <= len(sentence) <= 300 or any(m in sentence for m in SPONSOR_MARKERS):
                        continue
                    score = self.features.similarity(seed_features, self.features.features(sentence))
                    if sentence.endswith(("？", "?")):
                        score -= 0.04
                    candidate_sentences.append((score, chunk_idx, sentence))
            candidate_sentences.sort(reverse=True)

            excerpts: list[str] = []
            for _, chunk_idx, sentence in candidate_sentences:
                excerpt = self.sanitizer.clean_excerpt(sentence)
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
                    excerpt = self.sanitizer.clean_excerpt(sentence)
                    if excerpt not in excerpts:
                        excerpts.append(excerpt)
                    if len(excerpts) == 2:
                        break

            if len(excerpts) < 2:
                raise ValueError(f"Could not extract two distinct points for seed: {seed}")

            # Find position in cleaned transcript
            positions = []
            for e in excerpts:
                e_compact = re.sub(r"[\s\W_]+", "", e.lower())
                pos = cleaned_transcript_compact.find(e_compact[:20])
                if pos == -1:
                    pos = cleaned_transcript_compact.find(e_compact[:10])
                positions.append(pos if pos != -1 else 0)

            pos = min(positions)
            chapters.append({
                "position": pos,
                "title": seed,
                "excerpts": tuple(excerpts),
            })

        # Sort by position
        chapters.sort(key=lambda ch: ch["position"])

        return [
            ChapterEvidence(
                index=idx,
                seed_title=ch["title"],
                excerpts=ch["excerpts"],
                position=ch["position"],
            )
            for idx, ch in enumerate(chapters, 1)
        ]
