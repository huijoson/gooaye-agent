#!/usr/bin/env python3
"""Deterministically compose headings from exact phrases in both chapter excerpts."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTES_DIR = ROOT / "gooaye-youtube-notes/episodes"
ARCHIVE_PATH = ROOT / ".work/source/episodes.json"
OUTPUT_DIR = ROOT / ".work/grounded-headings"
GENERIC = re.compile(r"(?:我覺得|這個東西|這件事情|沒有辦法|接下來|聽眾問答|實務建議|本段重點|然後就是|所以就是)", re.I)
BAD_START = set("的了是在有就也都會要把跟和與及而但因為你我他它這那很還說講做去來")
BAD_END = set("的了是在有就也都會要把跟和與及而但因為你我他它這那很還說講做去來")


def parse_note(path: Path) -> list[list[str]]:
    text = path.read_text(encoding="utf-8")
    blocks = re.findall(r"^### \d+\. .+?\n\n((?:- .+\n?)+)", text, re.M)
    return [re.findall(r"^- (.+)$", block, re.M) for block in blocks]


def compact_with_map(text: str) -> tuple[str, list[int]]:
    chars, positions = [], []
    for index, char in enumerate(text):
        if re.match(r"[\u3400-\u9fffa-zA-Z0-9]", char):
            chars.append(char.lower())
            positions.append(index)
    return "".join(chars), positions


def compact(text: str) -> str:
    return compact_with_map(text)[0]


def exact_span(text: str, start: int, length: int) -> str:
    value, positions = compact_with_map(text)
    if start < 0 or start + length > len(value):
        raise ValueError("Invalid compact span")
    phrase = text[positions[start] : positions[start + length - 1] + 1]
    return phrase.strip().strip("，。！？!?；;：:、 ")


def ngrams(text: str, size: int) -> set[str]:
    value = compact(text)
    return {value[i:i + size] for i in range(len(value) - size + 1)}


def candidate_score(value: str, document_frequency: Counter[str], other: str = "") -> float:
    grams = [value[i:i + 4] for i in range(max(0, len(value) - 3))]
    rarity = sum(1 / math.sqrt(document_frequency.get(gram, 1)) for gram in grams)
    overlap = sum(1 for i in range(max(0, len(value) - 1)) if value[i:i + 2] in other)
    ascii_bonus = 2.5 if re.search(r"[a-z0-9]", value) else 0
    edge_penalty = (1.2 if value and value[0] in BAD_START else 0) + (1.2 if value and value[-1] in BAD_END else 0)
    return rarity + overlap * 1.8 + ascii_bonus + len(value) * 0.08 - edge_penalty


def shared_phrases(one: str, two: str, document_frequency: Counter[str]) -> list[tuple[float, str, str]]:
    c1, _ = compact_with_map(one); c2, _ = compact_with_map(two)
    candidates = []
    for size in range(min(12, len(c1), len(c2)), 4, -1):
        seen = set()
        for start in range(len(c1) - size + 1):
            value = c1[start:start + size]
            if value in seen or value not in c2 or GENERIC.search(value):
                continue
            seen.add(value)
            other_start = c2.find(value)
            p1, p2 = exact_span(one, start, size), exact_span(two, other_start, size)
            score = candidate_score(value, document_frequency, c2) + size * 0.5
            candidates.append((score, p1, p2))
    return sorted(candidates, reverse=True)


def independent_phrase(text: str, other: str, document_frequency: Counter[str]) -> str:
    value, _ = compact_with_map(text); other_value = compact(other)
    candidates = []
    max_size = min(12, len(value))
    for size in range(6, max_size + 1):
        for start in range(len(value) - size + 1):
            phrase_value = value[start:start + size]
            if GENERIC.search(phrase_value):
                continue
            phrase = exact_span(text, start, size)
            if not phrase or re.search(r"https?://", phrase):
                continue
            score = candidate_score(phrase_value, document_frequency, other_value)
            candidates.append((score, size, -start, phrase))
    if not candidates:
        raise ValueError(f"No phrase candidate: {text!r}")
    return max(candidates)[3]


def compose(p1: str, p2: str, summary: str, used: set[str]) -> str:
    same = compact(p1) == compact(p2)
    candidates = [p1] if same else [f"{p1}與{p2}", f"{p1}及{p2}", f"{p2}與{p1}", f"{p1}對照{p2}"]
    source = compact(summary)
    for title in candidates:
        value = compact(title)
        if 4 <= len(title) <= 40 and value not in used and not GENERIC.search(title) and not (len(value) >= 5 and value in source):
            used.add(value)
            return title
    title = f"{p2}對照{p1}"
    if compact(title) in used or not 4 <= len(title) <= 40:
        raise ValueError(f"Cannot compose unique heading: {p1!r}, {p2!r}")
    used.add(compact(title))
    return title


def main() -> None:
    summaries = {item["number"]: item["summary"] for item in json.loads(ARCHIVE_PATH.read_text())}
    episodes = []
    all_bullets = []
    for path in sorted(NOTES_DIR.glob("EP*.md")):
        number = int(path.stem[2:]); chapters = parse_note(path)
        if not chapters or any(len(chapter) != 2 for chapter in chapters):
            raise ValueError(f"Invalid evidence structure EP{number}")
        episodes.append((number, chapters)); all_bullets.extend(bullet for chapter in chapters for bullet in chapter)

    document_frequency: Counter[str] = Counter()
    for bullet in all_bullets:
        document_frequency.update(ngrams(bullet, 4))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    heading_count = shared_count = 0
    for number, chapters in episodes:
        headings, phrases, used = [], [], set()
        for one, two in chapters:
            shared = [
                candidate
                for candidate in shared_phrases(one, two, document_frequency)
                if compact(candidate[1]) not in compact(summaries[number])
            ]
            if shared:
                _, p1, p2 = shared[0]; shared_count += 1
            else:
                p1 = independent_phrase(one, two, document_frequency)
                p2 = independent_phrase(two, one, document_frequency)
            title = compose(p1, p2, summaries[number], used)
            headings.append(title); phrases.append({"phrase1": p1, "phrase2": p2})
        data = {
            "episode": number,
            "headings": headings,
            "evidence_phrases": phrases,
            "method": "deterministic_exact_phrases_from_both_excerpts",
        }
        (OUTPUT_DIR / f"EP{number:04d}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        heading_count += len(headings)
    print(f"episodes={len(episodes)} headings={heading_count} shared_phrase_headings={shared_count}")


if __name__ == "__main__":
    main()
