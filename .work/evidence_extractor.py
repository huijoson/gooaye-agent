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
        self.features = feature_extractor or TranscriptFeatureExtractor()
        self.segmenter = segmenter or TranscriptSegmenter(
            sanitizer=self.sanitizer,
            features=self.features,
        )

    def extract(
        self,
        transcript_or_summary: str = "",
        transcript: str | None = None,
        summary: str = "",
        target_chapters: int = 8,
        min_excerpts: int = 2,
        max_excerpts: int = 6,
    ) -> list[ChapterEvidence]:
        """Extract structured chapter evidence directly from transcript (and optional summary)."""
        if transcript is not None:
            raw_summary = transcript_or_summary
            raw_transcript = transcript
        else:
            raw_transcript = transcript_or_summary
            raw_summary = summary

        if not raw_transcript.strip():
            raise ValueError("Empty transcript")

        windows = self.segmenter.segment_semantic_chapters(
            transcript=raw_transcript,
            target_count=target_chapters,
            summary=raw_summary,
        )
        if not windows:
            raise ValueError("Could not segment transcript into windows")

        cleaned_transcript = self.sanitizer.clean(raw_transcript)
        cleaned_transcript_compact = re.sub(r"[\s\W_]+", "", cleaned_transcript.lower())
        normalized_summary = re.sub(r"\s+", "", raw_summary)

        chapters: list[dict] = []
        used_excerpts: set[str] = set()

        signoff_pattern = re.compile(
            r"^(?:好[，, ]*)?(?:那|這)?(?:節目|這集|本集)?(?:就先|就)?到這邊[，, ]*(?:大家)?(?:拜拜|掰掰|掰|再見|感謝大家的收聽|謝謝大家)[。！？!?]*$|^(?:好[，, ]*)?(?:那)?(?:接下來|接著)?我們(?:來)?進入 Q&A[。！？!?]*$",
            re.IGNORECASE,
        )

        for win in windows:
            candidate_sentences: list[tuple[float, str]] = []
            hint_features = self.features.features(win.topic_hint) if win.topic_hint else Counter()

            for sentence in win.sentences:
                if not 18 <= len(sentence) <= 320 or any(m in sentence for m in SPONSOR_MARKERS):
                    continue
                if signoff_pattern.search(sentence.strip()):
                    continue
                sent_features = self.features.features(sentence)
                score = len(sentence) / 100.0
                if hint_features:
                    score += self.features.similarity(hint_features, sent_features) * 2.0
                if sentence.endswith(("？", "?")):
                    score -= 0.1
                if re.search(r"\d+", sentence):
                    score += 0.05
                candidate_sentences.append((score, sentence))

            candidate_sentences.sort(key=lambda x: x[0], reverse=True)

            excerpts: list[str] = []
            for _, sentence in candidate_sentences:
                excerpt = self.sanitizer.clean_excerpt(sentence)
                normalized = re.sub(r"\s+", "", excerpt.rstrip("。"))
                if normalized in normalized_summary or normalized in used_excerpts:
                    continue
                if any(normalized in existing or existing in normalized for existing in used_excerpts):
                    continue
                excerpts.append(excerpt)
                used_excerpts.add(normalized)
                if len(excerpts) >= max_excerpts:
                    break

            if len(excerpts) < min_excerpts:
                for _, sentence in candidate_sentences:
                    excerpt = self.sanitizer.clean_excerpt(sentence)
                    if excerpt not in excerpts:
                        excerpts.append(excerpt)
                    if len(excerpts) >= min_excerpts:
                        break

            if len(excerpts) < min_excerpts:
                for s in win.sentences:
                    clean_s = self.sanitizer.clean_excerpt(s)
                    if clean_s and clean_s not in excerpts:
                        excerpts.append(clean_s)
                    if len(excerpts) >= min_excerpts:
                        break

            positions = []
            for e in excerpts:
                e_compact = re.sub(r"[\s\W_]+", "", e.lower())
                pos = cleaned_transcript_compact.find(e_compact[:20])
                if pos == -1:
                    pos = cleaned_transcript_compact.find(e_compact[:10])
                positions.append(pos if pos != -1 else win.position)

            pos = min(positions) if positions else win.position
            seed_title = win.topic_hint or (excerpts[0][:30] if excerpts else f"觀念焦點 {win.index}")

            chapters.append({
                "position": pos,
                "title": seed_title,
                "excerpts": tuple(excerpts),
            })

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
