#!/usr/bin/env python3
"""Fallback: generate one grounded heading per request for unresolved episodes using HeadingQualityEngine."""

from __future__ import annotations

import concurrent.futures
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from heading_quality_engine import HeadingQualityEngine

ROOT = Path(__file__).resolve().parent.parent
NOTES_DIR = ROOT / "gooaye-youtube-notes/episodes"
ARCHIVE_PATH = ROOT / ".work/source/episodes.json"
OUTPUT_DIR = ROOT / ".work/grounded-headings"
OLLAMA_URL = "http://127.0.0.1:11435/api/generate"
MODEL = "qwen3.5:4b"
engine = HeadingQualityEngine()

SCHEMA = {
    "type": "object",
    "required": ["heading"],
    "properties": {"heading": {"type": "string"}},
}
PROMPT = """/no_think
請只根據下方兩個完整逐字稿摘錄，替這一章命名。
- 標題 8–32 字，具體指出摘錄中的對象與觀念。
- 不補外部資訊；不使用「主題、其他、雜談、市場話題、聽眾、問答、QA、實務建議、本段重點」。
- 不以「另外、順帶、接著、轉向、並、後半、的、了、是」開頭。
- 書名號、引號、括號成對，不使用省略號，繁體中文。
- 禁止照抄「禁用摘要」內連續 5 字以上的片段；摘要只用來避字，不可作為內容依據。
只回傳 schema JSON。

摘錄一：{one}
摘錄二：{two}
禁用摘要：{summary}
{feedback}
"""


def parse_note(path: Path) -> list[list[str]]:
    text = path.read_text(encoding="utf-8")
    chapters = re.findall(r"^### \d+\. .+?\n\n((?:- .+\n?)+)", text, re.M)
    return [re.findall(r"^- (.+)$", block, re.M) for block in chapters]


def load_cached(number: int, chapter_count: int, summary: str) -> list[str] | None:
    path = OUTPUT_DIR / f"EP{number:04d}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        headings = data["headings"]
        evidence = parse_note(NOTES_DIR / f"EP{number:04d}.md")
        if len(headings) != chapter_count:
            return None
        if any(not engine.evaluate(heading, bullets, summary) for heading, bullets in zip(headings, evidence)):
            return None
        return headings
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None


def call(prompt: str) -> dict:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": SCHEMA,
        "options": {"temperature": 0.25, "num_ctx": 4096, "num_predict": 120},
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        wrapper = json.loads(response.read().decode("utf-8"))
    return json.loads(wrapper["response"])


def make_heading(number: int, index: int, evidence: list[str], summary: str) -> tuple[int, int, str]:
    manual_overrides = {
        (340, 3): "大型業者業務複雜不易分析",
        (356, 0): "企業演講提問揭露真實思維",
        (587, 0): "咖啡啤酒與站姿的階段變化",
    }
    if (number, index) in manual_overrides:
        heading = manual_overrides[(number, index)]
        if not engine.evaluate(heading, evidence, summary):
            raise RuntimeError(f"Manual heading invalid: {heading}")
        return number, index, heading

    feedback = ""
    last_errors = []
    for attempt in range(1, 7):
        try:
            result = call(PROMPT.format(one=evidence[0], two=evidence[1], summary=summary, feedback=feedback))
            heading = str(result["heading"]).strip()
            report = engine.diagnose(heading, evidence, summary)
            if report.is_valid:
                return number, index, heading
            last_errors = [report.feedback_message]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as error:
            last_errors = [str(error)]
        feedback = "前次錯誤：" + "、".join(last_errors) + "。請換一個更貼近摘錄的標題。"
        time.sleep(attempt)

    # Deterministic fallback if LLM attempts exhausted
    fallback = engine.repair("", evidence, summary)
    return number, index, fallback


def main() -> None:
    summaries = {item["number"]: item["summary"] for item in json.loads(ARCHIVE_PATH.read_text())}
    unresolved = []
    for path in sorted(NOTES_DIR.glob("EP*.md")):
        number = int(path.stem[2:])
        chapters = parse_note(path)
        if load_cached(number, len(chapters), summaries[number]) is None:
            unresolved.append((number, chapters))
    print("unresolved episodes:", [number for number, _ in unresolved], flush=True)

    results: dict[int, dict[int, str]] = {number: {} for number, _ in unresolved}
    jobs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for number, chapters in unresolved:
            for index, evidence in enumerate(chapters):
                jobs.append(executor.submit(make_heading, number, index, evidence, summaries[number]))
        for completed, future in enumerate(concurrent.futures.as_completed(jobs), 1):
            number, index, heading = future.result()
            results[number][index] = heading
            print(f"[{completed}/{len(jobs)}] EP{number} ch{index + 1}: {heading}", flush=True)

    for number, chapters in unresolved:
        headings = [results[number][index] for index in range(len(chapters))]
        if len({engine.compact(heading) for heading in headings}) != len(headings):
            raise RuntimeError(f"EP{number}: duplicate headings")
        path = OUTPUT_DIR / f"EP{number:04d}.json"
        path.write_text(
            json.dumps({"episode": number, "headings": headings, "model": MODEL, "fallback": "one_chapter_per_request"}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print("saved episodes:", len(unresolved))


if __name__ == "__main__":
    main()
