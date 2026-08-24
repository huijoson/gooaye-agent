#!/usr/bin/env python3
"""Build chapter headings only from exact phrases selected from both excerpts."""

from __future__ import annotations

import concurrent.futures
import json
import re
import threading
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTES_DIR = ROOT / "gooaye-youtube-notes/episodes"
ARCHIVE_PATH = ROOT / ".work/source/episodes.json"
OUTPUT_DIR = ROOT / ".work/grounded-headings"
OLLAMA_URL = "http://127.0.0.1:11435/api/generate"
MODEL = "qwen3.5:4b"
WORKERS = 4
BATCH_SIZE = 4
print_lock = threading.Lock()

SCHEMA = {
    "type": "object",
    "required": ["episodes"],
    "properties": {
        "episodes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["episode", "chapters"],
                "properties": {
                    "episode": {"type": "integer"},
                    "chapters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["phrase1", "phrase2"],
                            "properties": {
                                "phrase1": {"type": "string"},
                                "phrase2": {"type": "string"},
                            },
                        },
                    },
                },
            },
        }
    },
}

PROMPT = """/no_think
你是繁體中文 Podcast 索引編輯。下方每章恰有摘錄一、摘錄二，兩者都直接取自完整逐字稿。

你不是要改寫或摘要。你的工作是：
1. 從摘錄一原文逐字複製一個 4–12 字的具體關鍵短語到 phrase1。
2. 從摘錄二原文逐字複製一個 4–12 字的具體關鍵短語到 phrase2。
3. 短語必須是該摘錄中連續、完全相同的文字，不可改字、補字、翻譯或引入常識。
4. 優先選公司、人名、產品、產業、事件、策略、因果或結論；避開「我覺得」「這個東西」「接下來」「聽眾問答」等空泛過場。
5. 兩個短語合起來應能辨識本章內容；不要選純標點。
6. 集數、章數及順序必須與輸入完全一致，只回傳符合 schema 的 JSON。

{episodes}
"""

GENERIC = re.compile(r"^(?:我覺得|這個東西|這件事情|接下來|聽眾問答|實務建議|本段重點|沒有辦法|就是這樣)$", re.I)


def parse_note(path: Path) -> list[list[str]]:
    text = path.read_text(encoding="utf-8")
    blocks = re.findall(r"^### \d+\. .+?\n\n((?:- .+\n?)+)", text, re.M)
    return [re.findall(r"^- (.+)$", block, re.M) for block in blocks]


def compact(text: str) -> str:
    return "".join(re.findall(r"[\u3400-\u9fffa-zA-Z0-9]+", text)).lower()


def phrase_valid(phrase: object, excerpt: str) -> bool:
    if not isinstance(phrase, str):
        return False
    phrase = phrase.strip().strip("，。！？!?；;：:、")
    if not 4 <= len(compact(phrase)) <= 18 or GENERIC.fullmatch(phrase):
        return False
    return phrase in excerpt


def clean_phrase(phrase: str) -> str:
    return phrase.strip().strip("，。！？!?；;：:、")


def title_from_phrases(phrase1: str, phrase2: str, summary: str, used: set[str]) -> str:
    p1, p2 = clean_phrase(phrase1), clean_phrase(phrase2)
    candidates = []
    if p1 in p2:
        candidates.append(p2)
    elif p2 in p1:
        candidates.append(p1)
    else:
        candidates.extend((f"{p1}與{p2}", f"{p1}及{p2}", f"{p2}與{p1}"))
    summary_compact = compact(summary)
    for title in candidates:
        value = compact(title)
        if 4 <= len(title) <= 40 and value not in used and not (len(value) >= 5 and value in summary_compact):
            used.add(value)
            return title
    # A connector makes the title non-contiguous with source summary while all content phrases remain verbatim evidence.
    title = f"{p1}對照{p2}"
    if compact(title) in used:
        title = f"{p2}對照{p1}"
    if not 4 <= len(title) <= 40:
        raise ValueError(f"Cannot compose title from {p1!r}, {p2!r}")
    used.add(compact(title))
    return title


def format_episodes(items: list[dict]) -> str:
    sections = []
    for item in items:
        lines = [f"EP{item['number']}（{len(item['chapters'])} 章）"]
        for index, (one, two) in enumerate(item["chapters"], 1):
            lines.extend((f"章 {index}", f"摘錄一：{one}", f"摘錄二：{two}"))
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def call_model(items: list[dict]) -> dict:
    payload = {
        "model": MODEL,
        "prompt": PROMPT.format(episodes=format_episodes(items)),
        "stream": False,
        "think": False,
        "format": SCHEMA,
        "options": {"temperature": 0.1, "num_ctx": 16384, "num_predict": 1800},
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        return json.loads(json.loads(response.read().decode())["response"])


def parse_response(items: list[dict], response: dict) -> dict[int, list[tuple[str, str]]]:
    expected = {item["number"]: item for item in items}
    result = {}
    for episode in response.get("episodes", []):
        number = episode.get("episode")
        if number not in expected or number in result:
            continue
        chapters = episode.get("chapters")
        evidence = expected[number]["chapters"]
        if not isinstance(chapters, list) or len(chapters) != len(evidence):
            continue
        pairs = []
        for generated, (one, two) in zip(chapters, evidence):
            p1, p2 = generated.get("phrase1"), generated.get("phrase2")
            if not phrase_valid(p1, one) or not phrase_valid(p2, two):
                break
            pairs.append((clean_phrase(p1), clean_phrase(p2)))
        if len(pairs) == len(evidence):
            result[number] = pairs
    return result


def generate_batch(items: list[dict]) -> dict[int, list[tuple[str, str]]]:
    result = {}
    for _ in range(3):
        try:
            result.update(parse_response(items, call_model(items)))
        except Exception:
            pass
        if len(result) == len(items):
            return result
        items = [item for item in items if item["number"] not in result]
    return result


def generate_one_chapter(number: int, index: int, evidence: tuple[str, str]) -> tuple[str, str]:
    item = {"number": number, "chapters": [evidence]}
    for _ in range(8):
        result = generate_batch([item])
        if number in result:
            return result[number][0]
    raise RuntimeError(f"Could not select exact phrases for EP{number} chapter {index + 1}")


def main() -> None:
    summaries = {item["number"]: item["summary"] for item in json.loads(ARCHIVE_PATH.read_text())}
    items = []
    for path in sorted(NOTES_DIR.glob("EP*.md")):
        number = int(path.stem[2:])
        chapters = parse_note(path)
        if not chapters or any(len(chapter) != 2 for chapter in chapters):
            raise ValueError(f"Invalid note evidence EP{number}")
        items.append({"number": number, "chapters": [tuple(chapter) for chapter in chapters]})

    batches = [items[index:index + BATCH_SIZE] for index in range(0, len(items), BATCH_SIZE)]
    all_pairs: dict[int, list[tuple[str, str]]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(generate_batch, batch): batch for batch in batches}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            all_pairs.update(future.result())
            done += len(futures[future])
            with print_lock:
                print(f"batch progress {done}/{len(items)} valid={len(all_pairs)}", flush=True)

    unresolved = [item for item in items if item["number"] not in all_pairs]
    chapter_jobs = []
    for item in unresolved:
        for index, evidence in enumerate(item["chapters"]):
            chapter_jobs.append((item["number"], index, evidence))
    if chapter_jobs:
        recovered: dict[int, list[tuple[str, str] | None]] = {
            item["number"]: [None] * len(item["chapters"]) for item in unresolved
        }
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {
                executor.submit(generate_one_chapter, number, index, evidence): (number, index)
                for number, index, evidence in chapter_jobs
            }
            for future in concurrent.futures.as_completed(futures):
                number, index = futures[future]
                recovered[number][index] = future.result()
                print(f"fallback EP{number} ch{index + 1}", flush=True)
        for number, pairs in recovered.items():
            if any(pair is None for pair in pairs):
                raise RuntimeError(f"Incomplete fallback EP{number}")
            all_pairs[number] = pairs  # type: ignore[assignment]

    if len(all_pairs) != len(items):
        raise RuntimeError(f"Only generated {len(all_pairs)}/{len(items)} episodes")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for item in items:
        number = item["number"]
        pairs = all_pairs[number]
        used: set[str] = set()
        headings = [title_from_phrases(p1, p2, summaries[number], used) for p1, p2 in pairs]
        data = {
            "episode": number,
            "headings": headings,
            "evidence_phrases": [{"phrase1": p1, "phrase2": p2} for p1, p2 in pairs],
            "model": MODEL,
            "method": "exact_phrase_from_each_excerpt",
        }
        (OUTPUT_DIR / f"EP{number:04d}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"saved episodes={len(items)} headings={sum(len(v) for v in all_pairs.values())}")


if __name__ == "__main__":
    main()
