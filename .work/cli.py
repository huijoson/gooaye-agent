#!/usr/bin/env python3
"""Unified CLI for Gooaye Note Processing & Architecture Management."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from domain import QualityReport
from heading_quality_engine import HeadingQualityEngine
from heading_resolver import (
    CachedHeadingResolver,
    DeterministicHeadingResolver,
    CompositeHeadingResolver,
    OllamaHeadingResolver,
)
from episode_synthesizer import EpisodeNoteSynthesizer, OUTPUT_DIR, HEADINGS_CACHE_DIR


def cmd_synthesize(args: argparse.Namespace) -> None:
    synthesizer = EpisodeNoteSynthesizer()

    # Select resolver
    if args.resolver == "deterministic":
        resolver = DeterministicHeadingResolver(quality_engine=synthesizer.quality)
    elif args.resolver == "cache":
        resolver = CachedHeadingResolver(cache_dir=HEADINGS_CACHE_DIR, quality_engine=synthesizer.quality)
    elif args.resolver == "ollama":
        resolver = OllamaHeadingResolver(quality_engine=synthesizer.quality)
    else:
        resolver = CompositeHeadingResolver(cache_dir=HEADINGS_CACHE_DIR, quality_engine=synthesizer.quality)

    if args.episode:
        note = synthesizer.synthesize_episode(args.episode, resolver=resolver)
        if args.dry_run:
            print(note.render_markdown())
        else:
            ep_dir = args.output_dir / "episodes"
            ep_dir.mkdir(parents=True, exist_ok=True)
            out_file = ep_dir / f"EP{args.episode:04d}.md"
            out_file.write_text(note.render_markdown(), encoding="utf-8")
            print(f"Wrote EP{args.episode} note to {out_file}")
    else:
        start_time = time.time()
        print(f"Synthesizing all {len(synthesizer.episode_numbers)} episodes using {args.resolver} resolver (workers={args.workers})...")
        summary = synthesizer.synthesize_all(
            output_dir=args.output_dir,
            resolver=resolver,
            max_workers=args.workers,
        )
        elapsed = time.time() - start_time
        print(f"Successfully generated {summary.total_episodes} notes ({summary.total_chapters} chapters) in {elapsed:.2f}s.")
        print(f"Chapter distribution: {dict(sorted(summary.chapter_distribution.items()))}")


def cmd_audit(args: argparse.Namespace) -> None:
    synthesizer = EpisodeNoteSynthesizer()
    print("Auditing all episodes for heading defects...")
    result = synthesizer.audit()
    defects = result["defects"]
    print(f"\nAudit completed: {result['total_episodes']} episodes, {result['total_chapters']} chapters.")
    print(f"Defect count: {len(defects)}")
    if defects:
        print("\nDefects details:")
        for item in defects[:20]:
            print(f"  EP{item.get('episode')}: {item}")
        if len(defects) > 20:
            print(f"  ... and {len(defects) - 20} more.")
    else:
        print("All chapters pass 100% quality engine validation!")


def cmd_diagnose(args: argparse.Namespace) -> None:
    engine = HeadingQualityEngine()
    excerpts = args.excerpts or []
    report = engine.diagnose(args.heading, excerpts, summary=args.summary or "")

    print(f"\nHeading: {args.heading}")
    print(f"Valid: {report.is_valid}")
    print(f"Diagnostics: {report.feedback_message}")
    if not report.is_valid and len(excerpts) >= 2:
        repaired = engine.repair(args.heading, excerpts, summary=args.summary or "")
        print(f"Deterministic repair: {repaired}")


def cmd_doctor(args: argparse.Namespace) -> None:
    synthesizer = EpisodeNoteSynthesizer()
    print("Running system doctor checks...")
    checks = [
        ("Channel index", synthesizer.channel_path.exists(), f"Found {len(synthesizer._channel_entries)} entries"),
        ("Archive source", synthesizer.archive_path.exists(), f"Found {len(synthesizer._archive_entries)} entries"),
        ("Transcripts dir", synthesizer.transcript_dir.exists(), f"Found {len(list(synthesizer.transcript_dir.glob('EP*.md')))} transcripts"),
        ("Headings cache", synthesizer.cache_dir.exists(), f"Found {len(list(synthesizer.cache_dir.glob('EP*.json')))} cached heading files"),
    ]

    all_ok = True
    for name, ok, detail in checks:
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {name}: {detail}")
        if not ok:
            all_ok = False

    print(f"\nCommon valid episode count: {len(synthesizer.episode_numbers)}")
    if all_ok:
        print("System doctor: All data sources and components are healthy.")
    else:
        print("System doctor: Found issues in data sources.")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gooaye Note Synthesis & Architecture Management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # synthesize
    p_syn = subparsers.add_parser("synthesize", help="Synthesize Markdown notes")
    p_syn.add_argument("--episode", type=int, help="Synthesize a single episode number")
    p_syn.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Destination directory for notes")
    p_syn.add_argument("--resolver", choices=["composite", "cache", "deterministic", "ollama"], default="composite", help="Heading resolution strategy")
    p_syn.add_argument("--workers", type=int, default=8, help="Number of worker threads for batch generation")
    p_syn.add_argument("--dry-run", action="store_true", help="Print markdown to stdout instead of writing to disk")
    p_syn.set_defaults(func=cmd_synthesize)

    # audit
    p_audit = subparsers.add_parser("audit", help="Audit heading quality across the corpus")
    p_audit.set_defaults(func=cmd_audit)

    # diagnose
    p_diag = subparsers.add_parser("diagnose", help="Diagnose a specific heading candidate")
    p_diag.add_argument("--heading", required=True, type=str, help="Heading candidate string")
    p_diag.add_argument("--excerpts", nargs="+", help="Chapter excerpt sentences")
    p_diag.add_argument("--summary", type=str, default="", help="Episode summary for leakage check")
    p_diag.set_defaults(func=cmd_diagnose)

    # doctor
    p_doc = subparsers.add_parser("doctor", help="Check integrity of system components and datasets")
    p_doc.set_defaults(func=cmd_doctor)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
