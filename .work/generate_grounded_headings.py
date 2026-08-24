#!/usr/bin/env python3
"""Generate chapter headings from grounded transcript excerpts using HeadingQualityEngine, EpisodeNoteSynthesizer, and Ollama."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from heading_quality_engine import HeadingQualityEngine
from episode_synthesizer import EpisodeNoteSynthesizer, HEADINGS_CACHE_DIR

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_PATH = ROOT / ".work/source/episodes.json"
OUTPUT_DIR = HEADINGS_CACHE_DIR
OLLAMA_URL = "http://127.0.0.1:11435/api/generate"
MODEL = "qwen3.5:4b"
print_lock = threading.Lock()
engine = HeadingQualityEngine()
synthesizer = EpisodeNoteSynthesizer(quality_engine=engine)

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

PROMPT = """/no_think
你是繁體中文 Podcast 章節編輯。下方只提供從完整逐字稿抽出的每章兩個重點，請替每章重新命名。

規則：
1. 每章恰好一個標題，順序與輸入一致；不得增刪集數或章節。
2. 標題 8–32 字，必須點出該章實際談到的對象與觀念，並同時涵蓋兩個重點的共同主題。
3. 只能根據重點文字命名，不補外部知識，不使用未在重點出現的公司、人名或結論。
4. 禁止「主題、其他、雜談、市場話題、聽眾問答、實務建議、本段重點」等空泛詞；不要以「另外、順帶、接著、轉向、並、後半、的、了、是」開頭。
5. 不得用省略號截斷；書名號、引號與括號必須成對；全部用繁體中文。
6. 只回傳符合 schema 的 JSON。

{episodes}
"""


def load_cached(number: int, chapter_count: int, summary: str, evidence: list[list[str]]) -> list[str] | None:
    path = OUTPUT_DIR / f"EP{number:04d}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        headings = data["headings"]
        if len(headings) != chapter_count:
            return None
        if any(not engine.evaluate(heading, bullets, summary) for heading, bullets in zip(headings, evidence)):
            return None
        return headings
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None


def call_ollama(prompt: str) -> tuple[dict, dict]:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": SCHEMA,
        "options": {"temperature": 0.2, "num_ctx": 16_384, "num_predict": 1_600},
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        wrapper = json.loads(response.read().decode("utf-8"))
    return json.loads(wrapper["response"]), {
        key: wrapper.get(key)
        for key in ("prompt_eval_count", "eval_count", "total_duration")
    }


def format_batch(batch: list[dict], feedback: dict[int, list[str]] | None = None) -> str:
    sections = []
    for item in batch:
        lines = [f"EP{item['number']}（{len(item['chapters'])} 章）"]
        for index, bullets in enumerate(item["chapters"], 1):
            lines.append(f"章 {index}：")
            lines.extend(f"- {bullet}" for bullet in bullets)
        if feedback and item["number"] in feedback:
            lines.append("前次錯誤，必須修正：" + "；".join(feedback[item["number"]]))
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def validate_response(response: dict, batch: list[dict]) -> tuple[dict[int, list[str]], dict[int, list[str]]]:
    by_number = {}
    for item in response.get("episodes", []):
        if isinstance(item, dict) and isinstance(item.get("episode"), int):
            by_number[item["episode"]] = item.get("headings")
    valid = {}
    feedback = {}
    for item in batch:
        number = item["number"]
        headings = by_number.get(number)
        issues = []
        if not isinstance(headings, list) or len(headings) != len(item["chapters"]):
            issues.append(f"標題數應為 {len(item['chapters'])}")
        else:
            normalized_headings = [engine.compact(heading) for heading in headings if isinstance(heading, str)]
            if len(set(normalized_headings)) != len(headings):
                issues.append("同一集標題不可重複")
            for index, (heading, evidence) in enumerate(zip(headings, item["chapters"]), 1):
                if not isinstance(heading, str):
                    issues.append(f"第 {index} 章不是字串")
                    continue
                report = engine.diagnose(heading, evidence, item["summary"])
                if not report.is_valid:
                    issues.append(f"第 {index} 章 {heading!r}: {report.feedback_message}")
        if issues:
            feedback[number] = issues
        else:
            valid[number] = [heading.strip() for heading in headings]
    return valid, feedback


def save_heading(number: int, headings: list[str], metrics: dict) -> None:
    path = OUTPUT_DIR / f"EP{number:04d}.json"
    path.write_text(
        json.dumps({"episode": number, "headings": headings, "model": MODEL, "metrics": metrics}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def process_batch(batch: list[dict]) -> tuple[list[int], dict[int, list[str]]]:
    remaining = list(batch)
    completed = []
    last_feedback: dict[int, list[str]] = {}
    for attempt in range(1, 5):
        prompt = PROMPT.format(episodes=format_batch(remaining, last_feedback if attempt > 1 else None))
        try:
            response, metrics = call_ollama(prompt)
            valid, feedback = validate_response(response, remaining)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as error:
            valid, feedback = {}, {item["number"]: [f"API/JSON error: {error}"] for item in remaining}
            metrics = {}
        for number, headings in valid.items():
            save_heading(number, headings, metrics)
            completed.append(number)
        remaining = [item for item in remaining if item["number"] not in valid]
        if not remaining:
            return completed, {}
        last_feedback = feedback
        time.sleep(attempt)

    # Strategy 1 fallback: deterministic repair for any items still failing after LLM attempts
    for item in remaining:
        number = item["number"]
        used: set[str] = set()
        fallback_headings = []
        for bullets in item["chapters"]:
            repaired = engine.repair("", bullets, item["summary"], used_headings=used)
            fallback_headings.append(repaired)
            used.add(engine.compact(repaired))
        save_heading(number, fallback_headings, {"fallback": "deterministic_quality_engine_repair"})
        completed.append(number)

    return completed, {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=6)
    parser.add_argument("--episodes", help="Comma-separated episode numbers")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    summaries = {item["number"]: item["summary"] for item in json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))}
    requested = {int(value) for value in args.episodes.split(",")} if args.episodes else None
    items = []
    cached = 0
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for number in synthesizer.episode_numbers:
        if requested is not None and number not in requested:
            continue
        raw_chapters = synthesizer.extract_evidence(number)
        evidence_bullets = [list(ch["excerpts"]) for ch in raw_chapters]
        if not args.force and load_cached(number, len(evidence_bullets), summaries[number], evidence_bullets) is not None:
            cached += 1
            continue
        items.append({"number": number, "chapters": evidence_bullets, "summary": summaries[number]})

    batches = [items[index : index + args.batch_size] for index in range(0, len(items), args.batch_size)]
    print(f"episodes={len(items)}, cached={cached}, batches={len(batches)}", flush=True)
    failures = {}
    generated = 0
    start = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(process_batch, batch) for batch in batches]
        for completed_index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            completed, failed = future.result()
            generated += len(completed)
            failures.update(failed)
            with print_lock:
                rate = generated / max(0.001, time.monotonic() - start) * 60
                print(f"[{completed_index}/{len(batches)}] generated={generated}, failed={len(failures)}, rate={rate:.1f} ep/min", flush=True)
    print(f"Summary: generated={generated}, cached={cached}, failed={len(failures)}")


if __name__ == "__main__":
    main()
