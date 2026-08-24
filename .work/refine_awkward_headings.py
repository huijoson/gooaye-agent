#!/usr/bin/env python3
"""Refine mechanically awkward headings using HeadingQualityEngine, EpisodeNoteSynthesizer, and Ollama."""

from __future__ import annotations

import concurrent.futures
import json
import threading
import urllib.request
from pathlib import Path

from heading_quality_engine import HeadingQualityEngine
from episode_synthesizer import EpisodeNoteSynthesizer, HEADINGS_CACHE_DIR

ROOT = Path(__file__).resolve().parent.parent
OLLAMA_URL = "http://127.0.0.1:11435/api/generate"
MODEL = "qwen3.5:4b"
lock = threading.Lock()
engine = HeadingQualityEngine()
synthesizer = EpisodeNoteSynthesizer(quality_engine=engine)

SCHEMA = {
    "type": "object",
    "required": ["chapters"],
    "properties": {
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "title"],
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                },
            },
        }
    },
}

PROMPT = """/no_think
你是繁體中文 Podcast 章節編輯。每章只提供兩條完整逐字稿摘錄，請真正重新命名，寫一個自然、具體、完整的章節標題。
規則：
1. 標題 8–32 字，不可是殘句，不可以「的、了、在、是、個、些、中、下、或是、應該、直接」開頭。
2. 必須同時涵蓋摘錄一與摘錄二；兩條摘錄都必須各有至少一個連續二字詞直接出現在標題。
3. 只能用摘錄已出現的人名、公司、產品、數字與結論，不補外部資訊。
4. 禁止把摘錄一的字元切片加「與／及」再黏上摘錄二的字元切片；必須整理成完整名詞短語或自然句法。
5. 英文單字與專名必須完整，不可切成 Apple Watc、Ant Grou、Analysi 等半截；括號、書名號必須成對。
6. 禁止反引號、<seg、殘留逗號、破折號、省略號，也禁止「主題、雜談、市場話題、聽眾問答、QA、實務建議」等泛稱。
7. 不要保留「我、你、他、就是、說、覺得、東西、事情、狀況、樣子」等口語人稱或填充詞形成的長原句切片；請改寫成名詞短語。
8. 所有數字、百分比與單位必須忠實照摘錄，不可把 100 趴寫成一趴、5% 寫成五成，或混淆億與兆。
9. 每個 id 恰好回傳一個 title，順序不變。
10. 嚴格保留否定、假設、時間、主體、受詞與比較方向；不可把「不會／可能／有沒有」改成肯定斷言，不可交換行動者與受影響者。
11. 只能描述本章兩條摘錄，絕不可借用同集其他段落、摘要或常識補出公司、產品、原因、結果。若兩摘錄主題不同，請用兩個完整自然的名詞短語清楚並列，不可虛構兩者因果或從屬關係。
12. 禁止逐字稿聽寫錯詞、聽眾 ID、招呼客套、粗俗詞與殘破口語進標題；應在不增加事實的前提下改成正式繁體中文。阿拉伯數字、百分比、幣別、億兆、月份、型號須保留原值與掛載對象。
只輸出 schema JSON。

{chapters}"""


def call(items: list[dict]) -> dict:
    sections = []
    for x in items:
        sections.append(f"id: {x['id']}\n摘錄一：{x['bullets'][0]}\n摘錄二：{x['bullets'][1]}")
    payload = {
        "model": MODEL,
        "prompt": PROMPT.format(chapters="\n\n".join(sections)),
        "stream": False,
        "think": False,
        "format": SCHEMA,
        "options": {"temperature": 0.45, "num_ctx": 16384, "num_predict": 1800},
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(json.loads(r.read().decode())["response"])


def process(batch: list[dict]) -> tuple[dict[str, str], list[str]]:
    remaining = list(batch)
    out: dict[str, str] = {}
    for _ in range(5):
        try:
            response = call(remaining)
        except Exception:
            continue
        by = {
            x.get("id"): str(x.get("title", "")).strip()
            for x in response.get("chapters", [])
            if isinstance(x, dict)
        }
        for item in remaining:
            title = by.get(item["id"])
            if title and engine.evaluate(title, item["bullets"], item["summary"]):
                out[item["id"]] = title
        remaining = [x for x in remaining if x["id"] not in out]
        if not remaining:
            break
    return out, [x["id"] for x in remaining]


def main() -> None:
    summaries = {
        x["number"]: x["summary"]
        for x in json.loads((ROOT / ".work/source/episodes.json").read_text())
    }
    items = []
    audit_targets: dict[tuple[int, int], set[str]] = {}
    audit_specs = (
        (ROOT / ".work/heading-defects-audit.json", ("conversational_fragments", "whole_raw_headings", "hard_numeric_mismatches", "secondary_numeric_issues")),
        (ROOT / ".work/heading-defects-round3.json", ("oral_rewrite_failures", "connector_splices", "numeric_semantic_errors", "manual_spotcheck_errors", "format_issues")),
        (ROOT / ".work/heading-defects-exhaustive-001-175.json", ("defects",)),
        (ROOT / ".work/heading-defects-exhaustive-176-350.json", ("defects",)),
        (ROOT / ".work/heading-defects-exhaustive-351-525.json", ("defects",)),
        (ROOT / ".work/heading-defects-exhaustive-526-690.json", ("defects",)),
    )
    for audit_path, keys in audit_specs:
        if not audit_path.exists():
            continue
        audit = json.loads(audit_path.read_text())
        for key in keys:
            for row in audit.get(key, []):
                episode = int(str(row["episode"]).removeprefix("EP"))
                audit_targets.setdefault((episode, int(row["chapter"]) - 1), set()).add(row["title"])

    for path in sorted(HEADINGS_CACHE_DIR.glob("EP*.json")):
        n = int(path.stem[2:])
        if n not in synthesizer.episode_numbers:
            continue
        data = json.loads(path.read_text())
        raw_chapters = synthesizer.extract_evidence(n)
        ev = [list(ch["excerpts"]) for ch in raw_chapters]
        for i, (title, bullets) in enumerate(zip(data["headings"], ev)):
            is_valid = engine.evaluate(title, bullets, summaries[n])
            if title in audit_targets.get((n, i), set()) or not is_valid:
                items.append({
                    "id": f"EP{n:04d}-C{i+1}",
                    "number": n,
                    "index": i,
                    "title": title,
                    "bullets": bullets,
                    "summary": summaries[n],
                })

    print(f"targets: {len(items)}", flush=True)
    batches = [items[i : i + 4] for i in range(0, len(items), 4)]
    results: dict[str, str] = {}
    failures: list[str] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        fs = [ex.submit(process, b) for b in batches]
        for k, f in enumerate(concurrent.futures.as_completed(fs), 1):
            good, bad = f.result()
            results.update(good)
            failures.extend(bad)
            print(f"[{k}/{len(fs)}] valid={len(results)} failed_pending={len(failures)}", flush=True)

    changed_eps = set()
    for item in items:
        if item["id"] not in results:
            continue
        path = HEADINGS_CACHE_DIR / f"EP{item['number']:04d}.json"
        data = json.loads(path.read_text())
        data["headings"][item["index"]] = results[item["id"]]
        data["method"] = "natural_heading_refined_by_quality_engine"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        changed_eps.add(item["number"])

    print(f"saved: {len(results)}, episodes: {len(changed_eps)}, failed: {len(failures)}")
    if failures:
        print("failures:", ",".join(failures))


if __name__ == "__main__":
    main()
