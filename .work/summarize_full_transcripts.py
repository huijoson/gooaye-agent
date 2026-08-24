#!/usr/bin/env python3
"""Create grounded chapter notes from complete transcripts with local Ollama."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import re
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANNEL_PATH = ROOT / ".work/channel.json"
ARCHIVE_PATH = ROOT / ".work/source/episodes.json"
TRANSCRIPT_DIR = ROOT / ".work/full-transcripts"
OUTPUT_DIR = ROOT / ".work/full-notes"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "qwen3.5:4b"
MAX_CONTEXT_CHARS = 9_000
print_lock = threading.Lock()

SCHEMA = {
    "type": "object",
    "required": ["summary", "chapters"],
    "properties": {
        "summary": {"type": "string"},
        "chapters": {
            "type": "array",
            "minItems": 3,
            "maxItems": 6,
            "items": {
                "type": "object",
                "required": ["title", "concepts"],
                "properties": {
                    "title": {"type": "string"},
                    "concepts": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 3,
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
}

PROMPT = """/no_think
你是繁體中文 Podcast 內容編輯。請根據「完整逐字稿檢索片段」重新整理本集摘要與章節觀念；來源摘要只能協助辨認主題，禁止照抄。

規則：
1. 依片段標示的原始位置與節目討論順序，產出 3–6 章，不虛構時間碼。
2. 每章標題 6–20 字且具體；禁止使用「主題」「其他」「雜談」「Q&A」等空泛標題，也不要截斷詞語。
3. 每章 2–3 個 concepts；每點 25–60 字，重述逐字稿中的論點、理由、例子、風險或結論，至少帶入一個來源摘要沒有明說的具體脈絡。
4. summary 100–180 字，須根據逐字稿片段重新撰寫，不能複製來源摘要句子。
5. 忽略純贊助口播、片頭片尾與沒有內容的寒暄。專有名詞不確定時保守表述，不得補充逐字稿外知識。
6. 全部使用繁體中文，只回傳符合 schema 的 JSON。

來源摘要（只作檢索主題提示，不可照抄）：
{source_summary}

完整逐字稿檢索片段（已按原始順序排列）：
{evidence}
"""


def public_episode_numbers() -> set[int]:
    channel = json.loads(CHANNEL_PATH.read_text(encoding="utf-8"))
    numbers = set()
    for entry in channel["entries"]:
        match = re.search(r"\bEP\s*(\d+)\b", entry.get("title", ""), re.I)
        if not match:
            raise ValueError(f"Cannot parse episode number: {entry.get('title')!r}")
        numbers.add(int(match.group(1)))
    return numbers


def normalize_transcript(text: str) -> str:
    text = re.sub(r"^#{1,6}\s+.*$", "", text, flags=re.M)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_chunks(text: str, target: int = 480) -> list[str]:
    sentences = re.split(r"(?<=[。！？!?])\s*", normalize_transcript(text))
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if current and size + len(sentence) > target:
            chunks.append("".join(current))
            current, size = [], 0
        current.append(sentence)
        size += len(sentence)
    if current:
        chunks.append("".join(current))
    return chunks


def split_seed(summary: str) -> list[str]:
    parts = re.split(r"(?<=[。！？])\s*|[；;]", summary)
    parts = [part.strip(" ，、。；;") for part in parts if len(part.strip(" ，、。；;")) >= 12]
    if len(parts) < 3:
        clauses = [part.strip() for part in re.split(r"[，、]", summary) if len(part.strip()) >= 10]
        if clauses:
            group_size = max(1, math.ceil(len(clauses) / 4))
            parts = ["、".join(clauses[i : i + group_size]) for i in range(0, len(clauses), group_size)]
    return parts[:6] or [summary]


def features(text: str) -> Counter[str]:
    compact = re.sub(r"\s+", "", text.lower())
    result: Counter[str] = Counter()
    for token in re.findall(r"[a-z][a-z0-9.+-]{1,}|\d+(?:\.\d+)?", compact):
        result[token] += 4
    chinese = "".join(re.findall(r"[\u3400-\u9fff]", compact))
    for size, weight in ((2, 1), (3, 2)):
        for index in range(len(chinese) - size + 1):
            result[chinese[index : index + size]] += weight
    return result


def similarity(seed_features: Counter[str], chunk_features: Counter[str]) -> float:
    if not seed_features or not chunk_features:
        return 0.0
    overlap = sum(min(weight, chunk_features.get(term, 0)) for term, weight in seed_features.items())
    return overlap / max(1, sum(seed_features.values()))


def retrieve_evidence(summary: str, transcript: str) -> str:
    chunks = make_chunks(transcript)
    if not chunks:
        raise ValueError("Transcript has no content")
    chunk_features = [features(chunk) for chunk in chunks]
    selected: set[int] = set()

    seeds = split_seed(summary)
    for seed_index, seed in enumerate(seeds):
        seed_features = features(seed)
        ranked = sorted(
            range(len(chunks)),
            key=lambda index: similarity(seed_features, chunk_features[index]),
            reverse=True,
        )
        chosen = 0
        for index in ranked:
            if any(abs(index - existing) <= 1 for existing in selected):
                continue
            selected.add(index)
            chosen += 1
            if chosen == 2:
                break
        if chosen == 0:
            selected.add(round((seed_index + 1) * (len(chunks) - 1) / (len(seeds) + 1)))

    # Add broad coverage so the model can see meaningful topics omitted by the
    # third-party source summary. Avoid the first 5%, which is often an ad.
    for fraction in (0.08, 0.25, 0.45, 0.65, 0.82, 0.94):
        selected.add(min(len(chunks) - 1, round(fraction * (len(chunks) - 1))))

    # Include one neighboring chunk for local context, then enforce size.
    expanded = set(selected)
    for index in list(selected):
        if index > 0:
            expanded.add(index - 1)
        if index + 1 < len(chunks):
            expanded.add(index + 1)

    ordered = sorted(expanded)
    if sum(len(chunks[index]) for index in ordered) > MAX_CONTEXT_CHARS:
        priority = set(selected)
        kept: list[int] = []
        used = 0
        for index in sorted(ordered, key=lambda item: (item not in priority, item)):
            if used + len(chunks[index]) <= MAX_CONTEXT_CHARS:
                kept.append(index)
                used += len(chunks[index])
        ordered = sorted(kept)

    lines = []
    for index in ordered:
        position = round(index * 100 / max(1, len(chunks) - 1))
        lines.append(f"[原文位置 {position}%] {chunks[index]}")
    return "\n\n".join(lines)


def validate_note(note: dict, source_summary: str) -> list[str]:
    errors = []
    summary = str(note.get("summary", "")).strip()
    chapters = note.get("chapters")
    if len(summary) < 60:
        errors.append("summary too short")
    if re.sub(r"\s+", "", summary) == re.sub(r"\s+", "", source_summary):
        errors.append("summary copied source verbatim")
    if not isinstance(chapters, list) or not 3 <= len(chapters) <= 6:
        errors.append("chapter count outside 3-6")
        return errors
    forbidden = re.compile(r"^(?:主題|其他|雜談|Q\s*&?\s*A|問答)(?:\s*\d+)?$", re.I)
    for index, chapter in enumerate(chapters, 1):
        title = str(chapter.get("title", "")).strip()
        concepts = chapter.get("concepts")
        if len(title) < 4 or forbidden.fullmatch(title):
            errors.append(f"chapter {index} invalid title")
        if not isinstance(concepts, list) or not 2 <= len(concepts) <= 3:
            errors.append(f"chapter {index} invalid concepts")
            continue
        for concept in concepts:
            concept = str(concept).strip()
            if len(concept) < 15:
                errors.append(f"chapter {index} concept too short")
            if concept in source_summary:
                errors.append(f"chapter {index} concept copied from source summary")
    return errors


def call_ollama(prompt: str) -> tuple[dict, dict]:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": SCHEMA,
        "options": {
            "temperature": 0.15,
            "num_ctx": 16_384,
            "num_predict": 850,
        },
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        wrapper = json.loads(response.read().decode("utf-8"))
    note = json.loads(wrapper["response"])
    metrics = {
        key: wrapper.get(key)
        for key in ("prompt_eval_count", "prompt_eval_duration", "eval_count", "eval_duration", "total_duration")
    }
    return note, metrics


def process_episode(episode: dict, force: bool = False) -> tuple[int, str, float]:
    number = episode["number"]
    output_path = OUTPUT_DIR / f"EP{number:04d}.json"
    if output_path.exists() and not force:
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            if not validate_note(existing, episode["summary"]):
                return number, "cached", 0.0
        except (json.JSONDecodeError, OSError):
            pass

    transcript_path = TRANSCRIPT_DIR / f"EP{number:04d}.md"
    transcript = transcript_path.read_text(encoding="utf-8")
    evidence = retrieve_evidence(episode["summary"], transcript)
    prompt = PROMPT.format(source_summary=episode["summary"], evidence=evidence)

    started = time.monotonic()
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            note, metrics = call_ollama(prompt)
            errors = validate_note(note, episode["summary"])
            if errors:
                raise ValueError("; ".join(errors))
            note["_provenance"] = {
                "model": MODEL,
                "transcript_file": transcript_path.name,
                "source_summary_used_as_query": True,
                "evidence_chars": len(evidence),
                "metrics": metrics,
            }
            output_path.write_text(json.dumps(note, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return number, "generated", time.monotonic() - started
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, KeyError) as error:
            last_error = error
            time.sleep(attempt * 2)
    return number, f"failed: {last_error}", time.monotonic() - started


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--episodes", help="Comma-separated episode numbers")
    args = parser.parse_args()

    public = public_episode_numbers()
    archives = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    episodes = [episode for episode in archives if episode["number"] in public]
    if args.episodes:
        requested = {int(value) for value in args.episodes.split(",")}
        episodes = [episode for episode in episodes if episode["number"] in requested]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    missing = [episode["number"] for episode in episodes if not (TRANSCRIPT_DIR / f"EP{episode['number']:04d}.md").exists()]
    if missing:
        raise SystemExit(f"Missing transcripts: {missing}")

    counts = Counter()
    failures = []
    start = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(process_episode, episode, args.force): episode["number"]
            for episode in episodes
        }
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            number, status, elapsed = future.result()
            completed += 1
            counts[status.split(":", 1)[0]] += 1
            if status.startswith("failed"):
                failures.append((number, status))
            with print_lock:
                rate = completed / max(0.001, time.monotonic() - start) * 60
                print(f"[{completed}/{len(episodes)}] EP{number}: {status} ({elapsed:.1f}s), {rate:.1f} ep/min", flush=True)

    print("Summary:", dict(counts))
    if failures:
        for number, status in failures:
            print(f"EP{number}: {status}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
