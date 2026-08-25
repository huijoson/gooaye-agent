"""Takeaway resolvers - Resolution strategies for chapter core takeaways (Cache, Deterministic, and Composite)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

from domain import EpisodeMetadata, ChapterEvidence
from takeaway_quality_engine import TakeawayQualityEngine

logger = logging.getLogger(__name__)


def _extract_excerpts(item: ChapterEvidence | dict) -> tuple[str, ...]:
    """Helper to uniformly extract excerpts from ChapterEvidence or dict."""
    if isinstance(item, ChapterEvidence):
        return item.excerpts
    return tuple(item.get("excerpts", ()))


@runtime_checkable
class TakeawayResolver(Protocol):
    """Protocol defining the takeaway resolution seam."""

    def resolve(
        self,
        metadata: EpisodeMetadata,
        raw_chapters: Sequence[ChapterEvidence | dict],
    ) -> list[str]: ...


class CachedTakeawayResolver:
    """Load takeaways from local cache directory with quality validation."""

    def __init__(
        self,
        cache_dir: Path,
        quality_engine: TakeawayQualityEngine | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.quality = quality_engine or TakeawayQualityEngine()

    def resolve(
        self,
        metadata: EpisodeMetadata,
        raw_chapters: Sequence[ChapterEvidence | dict],
    ) -> list[str] | None:
        cache_path = self.cache_dir / f"EP{metadata.number:04d}.json"
        if not cache_path.exists():
            return None
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            takeaways = data.get("takeaways")
            if data.get("episode") != metadata.number or not isinstance(takeaways, list):
                return None
            if len(takeaways) != len(raw_chapters):
                return None
            for takeaway, ch in zip(takeaways, raw_chapters):
                excerpts = _extract_excerpts(ch)
                if not self.quality.evaluate(takeaway, excerpts):
                    return None
            return [t.strip() for t in takeaways]
        except Exception as e:
            logger.debug(f"Failed to read takeaway cache for EP{metadata.number}: {e}")
            return None


class DeterministicTakeawayResolver:
    """Synthesize takeaways deterministically using TakeawayQualityEngine."""

    def __init__(self, quality_engine: TakeawayQualityEngine | None = None) -> None:
        self.quality = quality_engine or TakeawayQualityEngine()

    def resolve(
        self,
        metadata: EpisodeMetadata,
        raw_chapters: Sequence[ChapterEvidence | dict],
    ) -> list[str]:
        takeaways: list[str] = []
        for ch in raw_chapters:
            excerpts = _extract_excerpts(ch)
            takeaway = self.quality.extract_deterministic_takeaway(excerpts)
            takeaways.append(takeaway)
        return takeaways


class CompositeTakeawayResolver:
    """Composite resolver: Primary resolver with fallback to secondary resolver."""

    def __init__(
        self,
        primary: TakeawayResolver,
        secondary: TakeawayResolver,
        quality_engine: TakeawayQualityEngine | None = None,
    ) -> None:
        self.primary = primary
        self.secondary = secondary
        self.quality = quality_engine or TakeawayQualityEngine()

    def resolve(
        self,
        metadata: EpisodeMetadata,
        raw_chapters: Sequence[ChapterEvidence | dict],
    ) -> list[str]:
        try:
            candidates = self.primary.resolve(metadata, raw_chapters)
            if candidates is not None and len(candidates) == len(raw_chapters):
                all_valid = True
                for t, ch in zip(candidates, raw_chapters):
                    excerpts = _extract_excerpts(ch)
                    if not self.quality.evaluate(t, excerpts):
                        all_valid = False
                        break
                if all_valid:
                    return candidates
        except Exception as e:
            logger.debug(f"Primary takeaway resolver failed for EP{metadata.number}: {e}")

        return self.secondary.resolve(metadata, raw_chapters)
