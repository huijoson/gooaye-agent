"""Heading resolvers - Resolution strategies for chapter headings (Cache, Deterministic, Ollama/LLM, and Composite)."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

from domain import EpisodeMetadata, ChapterEvidence
from heading_quality_engine import HeadingQualityEngine

logger = logging.getLogger(__name__)


def _extract_excerpts_and_title(item: ChapterEvidence | dict) -> tuple[tuple[str, str], str]:
    """Helper to uniformly extract excerpts and seed title from ChapterEvidence or dict."""
    if isinstance(item, ChapterEvidence):
        return item.excerpts, item.seed_title
    return tuple(item.get("excerpts", ())), item.get("title", "")


@runtime_checkable
class HeadingResolver(Protocol):
    """Protocol defining the heading resolution seam."""

    def resolve(
        self,
        metadata: EpisodeMetadata,
        raw_chapters: Sequence[ChapterEvidence | dict],
    ) -> list[str]: ...


class CachedHeadingResolver:
    """Load headings from local cache directory with quality validation."""

    def __init__(
        self,
        cache_dir: Path,
        quality_engine: HeadingQualityEngine | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.quality = quality_engine or HeadingQualityEngine()

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
            headings = data.get("headings")
            if data.get("episode") != metadata.number or not isinstance(headings, list):
                return None
            if len(headings) != len(raw_chapters):
                return None
            for heading, ch in zip(headings, raw_chapters):
                excerpts, _ = _extract_excerpts_and_title(ch)
                if not self.quality.evaluate(heading, excerpts, metadata.summary):
                    return None
            return [h.strip() for h in headings]
        except Exception as e:
            logger.debug(f"Failed to read cache for EP{metadata.number}: {e}")
            return None


class DeterministicHeadingResolver:
    """Synthesize headings deterministically using HeadingQualityEngine."""

    def __init__(self, quality_engine: HeadingQualityEngine | None = None) -> None:
        self.quality = quality_engine or HeadingQualityEngine()

    def resolve(
        self,
        metadata: EpisodeMetadata,
        raw_chapters: Sequence[ChapterEvidence | dict],
    ) -> list[str]:
        headings: list[str] = []
        used: set[str] = set()
        for ch in raw_chapters:
            excerpts, title = _extract_excerpts_and_title(ch)
            repaired = self.quality.repair(
                title,
                excerpts,
                metadata.summary,
                used_headings=used,
            )
            headings.append(repaired)
            used.add(self.quality.compact(repaired))
        return headings


class CompositeHeadingResolver:
    """Composite resolver: Primary resolver with fallback to secondary resolver."""

    def __init__(
        self,
        primary: HeadingResolver | None = None,
        fallback: HeadingResolver | None = None,
        cache_dir: Path | None = None,
        quality_engine: HeadingQualityEngine | None = None,
    ) -> None:
        self.quality = quality_engine or HeadingQualityEngine()
        if primary is not None:
            self.primary = primary
        elif cache_dir is not None:
            self.primary = CachedHeadingResolver(cache_dir=cache_dir, quality_engine=self.quality)
        else:
            self.primary = None

        self.fallback = fallback or DeterministicHeadingResolver(quality_engine=self.quality)

    def resolve(
        self,
        metadata: EpisodeMetadata,
        raw_chapters: Sequence[ChapterEvidence | dict],
    ) -> list[str]:
        if self.primary is not None:
            try:
                res = self.primary.resolve(metadata, raw_chapters)
                if res is not None:
                    return res
            except Exception as e:
                logger.debug(f"Primary resolver failed for EP{metadata.number}: {e}")

        return self.fallback.resolve(metadata, raw_chapters)


class OllamaHeadingResolver:
    """Resolve chapter headings using an Ollama LLM endpoint with quality engine feedback retries."""

    DEFAULT_URL = "http://127.0.0.1:11435/api/generate"
    DEFAULT_MODEL = "qwen3.5:4b"

    SCHEMA = {
        "type": "object",
        "required": ["episodes"],
        "properties": {
            "episodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["episode", "headings"],
                    "properties": {
                        "episode": {"type": "integer"},
                        "headings": {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        },
    }

    def __init__(
        self,
        endpoint_url: str = DEFAULT_URL,
        model: str = DEFAULT_MODEL,
        max_retries: int = 2,
        quality_engine: HeadingQualityEngine | None = None,
        fallback_resolver: HeadingResolver | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.model = model
        self.max_retries = max_retries
        self.quality = quality_engine or HeadingQualityEngine()
        self.fallback = fallback_resolver or DeterministicHeadingResolver(quality_engine=self.quality)

    def _build_prompt(
        self,
        metadata: EpisodeMetadata,
        raw_chapters: Sequence[ChapterEvidence | dict],
        feedback: str = "",
    ) -> str:
        items = []
        for ch in raw_chapters:
            excerpts, _ = _extract_excerpts_and_title(ch)
            items.append({"points": list(excerpts)})
        payload = json.dumps([{"episode": metadata.number, "chapters": items}], ensure_ascii=False)

        feedback_instruction = f"\n前次瑕疵診斷反饋：{feedback}\n請修正上述問題，重新命名。" if feedback else ""

        return f"""/no_think
你是繁體中文 Podcast 章節編輯。下方只提供從完整逐字稿抽出的每章兩個重點，請替每章重新命名。

規則：
1. 每章恰好一個標題，順序與輸入一致；不得增刪集數或章節。
2. 標題 8–32 字，必須點出該章實際談到的對象與觀念，並同時涵蓋兩個重點的共同主題。
3. 只能根據重點文字命名，不補外部知識，不使用未在重點出現的公司、人名或結論。
4. 禁止「主題、其他、雜談、市場話題、聽眾問答、實務建議、本段重點」等空泛詞；不要以「另外、順帶、接著、轉向、並、後半、的、了、是」開頭。
5. 不得用省略號截斷；書名號、引號與括號必須成對；全部用繁體中文。
6. 禁止把長口語句片段直接黏合；若兩摘錄不同主題，請以名詞短語自然並列。
7. 只回傳符合 schema 的 JSON。{feedback_instruction}

{payload}
"""

    def resolve(
        self,
        metadata: EpisodeMetadata,
        raw_chapters: Sequence[ChapterEvidence | dict],
    ) -> list[str]:
        feedback = ""
        for attempt in range(self.max_retries + 1):
            try:
                prompt = self._build_prompt(metadata, raw_chapters, feedback=feedback)
                req_data = json.dumps({
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": self.SCHEMA,
                    "options": {"temperature": 0.2, "seed": 42},
                }).encode("utf-8")

                req = urllib.request.Request(
                    self.endpoint_url,
                    data=req_data,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw_resp = json.loads(resp.read().decode("utf-8"))
                    res_body = json.loads(raw_resp.get("response", "{}"))
                    ep_list = res_body.get("episodes", [])
                    if ep_list and "headings" in ep_list[0]:
                        headings = ep_list[0]["headings"]
                        if len(headings) == len(raw_chapters):
                            # Validate each heading
                            all_valid = True
                            defect_messages = []
                            for idx, (h, ch) in enumerate(zip(headings, raw_chapters), 1):
                                excerpts, _ = _extract_excerpts_and_title(ch)
                                report = self.quality.diagnose(h, excerpts, metadata.summary)
                                if not report.is_valid:
                                    all_valid = False
                                    defect_messages.append(f"第 {idx} 章「{h}」：{report.feedback_message}")

                            if all_valid:
                                return [h.strip() for h in headings]
                            feedback = "；".join(defect_messages)
            except Exception as e:
                logger.debug(f"Ollama call failed on attempt {attempt}: {e}")

        # Fallback to deterministic resolver
        return self.fallback.resolve(metadata, raw_chapters)
