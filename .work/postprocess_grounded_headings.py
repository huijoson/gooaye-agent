#!/usr/bin/env python3
"""Repair natural headings using HeadingQualityEngine and EpisodeNoteSynthesizer."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from heading_quality_engine import HeadingQualityEngine
from episode_synthesizer import EpisodeNoteSynthesizer, HEADINGS_CACHE_DIR

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_PATH = ROOT / ".work/source/episodes.json"
OUTPUT_DIR = HEADINGS_CACHE_DIR


def main() -> None:
    synthesizer = EpisodeNoteSynthesizer()
    summaries = {item["number"]: item["summary"] for item in json.loads(ARCHIVE_PATH.read_text())}
    all_bullets = []
    evidence_by_number = {}

    for number in synthesizer.episode_numbers:
        raw_chapters = synthesizer.extract_evidence(number)
        bullets = [list(ch["excerpts"]) for ch in raw_chapters]
        evidence_by_number[number] = bullets
        for b in bullets:
            all_bullets.extend(b)

    frequency: Counter[str] = Counter()
    for bullet in all_bullets:
        val = HeadingQualityEngine.compact(bullet)
        frequency.update({val[i : i + 4] for i in range(max(0, len(val) - 3))})

    engine = HeadingQualityEngine(corpus_frequencies=frequency)

    changed_episodes = changed_headings = 0
    for path in sorted(OUTPUT_DIR.glob("EP*.json")):
        number = int(path.stem[2:])
        if number not in evidence_by_number:
            continue
        data = json.loads(path.read_text())
        headings = data["headings"]
        evidence = evidence_by_number[number]
        if len(headings) != len(evidence):
            raise ValueError(f"Heading count mismatch EP{number}")
        original = list(headings)
        repaired = []
        used = set()
        for title, bullets in zip(headings, evidence):
            if engine.evaluate(title, bullets, summaries[number]) and engine.compact(title) not in used:
                new_title = title
            else:
                new_title = engine.repair(title, bullets, summaries[number], used_headings=used)
                changed_headings += 1
            repaired.append(new_title)
            used.add(engine.compact(new_title))
        if repaired != original:
            changed_episodes += 1
            data["original_headings"] = original
            data["headings"] = repaired
            data["method"] = "natural_heading_repaired_by_quality_engine"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"changed_episodes={changed_episodes} changed_headings={changed_headings}")


if __name__ == "__main__":
    main()
