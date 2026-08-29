#!/usr/bin/env python3
"""Unified CLI for Gooaye Note Processing & Architecture Management."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from domain import QualityReport
from heading_quality_engine import HeadingQualityEngine
from takeaway_quality_engine import TakeawayQualityEngine
from heading_resolver import (
    CachedHeadingResolver,
    DeterministicHeadingResolver,
    CompositeHeadingResolver,
    OllamaHeadingResolver,
)
from takeaway_resolver import (
    CachedTakeawayResolver,
    DeterministicTakeawayResolver,
    CompositeTakeawayResolver,
)
from episode_synthesizer import EpisodeNoteSynthesizer, OUTPUT_DIR, HEADINGS_CACHE_DIR
from episode_acquirer import (
    ARCHIVE_EPISODES_URL,
    ARCHIVE_INDEX_URL,
    SOUNDON_FEED_URL,
    YOUTUBE_FEED_URL,
    EpisodeAcquirer,
    EpisodeAcquisitionError,
    UrlLibHttpClient,
)
from episode_source_repository import EpisodeSourceError, EpisodeSourceRepository


ROOT = Path(__file__).resolve().parent.parent


def positive_episode_number(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("episode number must be positive")
    return number


def cmd_download(args: argparse.Namespace) -> None:
    work_dir = Path(os.environ.get("GOOAYE_WORK_DIR", ROOT / ".work"))
    archive_episodes_url = os.environ.get(
        "GOOAYE_ARCHIVE_EPISODES_URL",
        ARCHIVE_EPISODES_URL,
    )
    archive_parts = urlsplit(archive_episodes_url)
    archive_base_url = f"{archive_parts.scheme}://{archive_parts.netloc}/"
    repository = EpisodeSourceRepository(
        snapshot_root=work_dir / "episode-sources",
        legacy_channel_path=work_dir / "channel.json",
        legacy_archive_path=work_dir / "source" / "episodes.json",
        legacy_transcript_dir=work_dir / "full-transcripts",
        archive_base_url=archive_base_url,
    )
    acquirer = EpisodeAcquirer(
        repository=repository,
        http_client=UrlLibHttpClient(),
        youtube_feed_url=os.environ.get(
            "GOOAYE_YOUTUBE_FEED_URL",
            YOUTUBE_FEED_URL,
        ),
        soundon_feed_url=os.environ.get(
            "GOOAYE_SOUNDON_FEED_URL",
            SOUNDON_FEED_URL,
        ),
        archive_index_url=os.environ.get(
            "GOOAYE_ARCHIVE_INDEX_URL",
            ARCHIVE_INDEX_URL,
        ),
        archive_episodes_url=archive_episodes_url,
    )

    try:
        result = (
            acquirer.acquire_latest(force=args.force)
            if args.latest
            else acquirer.acquire(args.episode, force=args.force)
        )
    except (EpisodeAcquisitionError, EpisodeSourceError) as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"EP{result.number} source snapshot: {result.status}")
    print(f"youtube_id: {result.youtube_id}")
    print(f"duration_seconds: {result.duration_seconds}")
    print(f"Path: {result.snapshot_path}")
    print("verification: OK")


def cmd_synthesize(args: argparse.Namespace) -> None:
    synthesizer = EpisodeNoteSynthesizer()
    out_dir = args.out_dir or args.output_dir

    # Select heading resolver
    if args.resolver == "deterministic":
        resolver = DeterministicHeadingResolver(quality_engine=synthesizer.quality)
    elif args.resolver == "cache":
        resolver = CachedHeadingResolver(cache_dir=HEADINGS_CACHE_DIR, quality_engine=synthesizer.quality)
    elif args.resolver == "ollama":
        resolver = OllamaHeadingResolver(quality_engine=synthesizer.quality)
    else:
        resolver = CompositeHeadingResolver(cache_dir=HEADINGS_CACHE_DIR, quality_engine=synthesizer.quality)

    target_episodes = []
    if args.episode:
        target_episodes = [args.episode]
    elif args.episodes:
        target_episodes = args.episodes

    if len(target_episodes) == 1 and args.dry_run:
        note = synthesizer.synthesize_episode(target_episodes[0], resolver=resolver)
        print("=== SLIM NAVIGATION LAYER ===")
        print(note.render_markdown(mode="slim"))
        print("\n=== FULL DEEP CONTEXT LAYER ===")
        print(note.render_markdown(mode="full"))
    elif target_episodes:
        start_time = time.time()
        print(f"Synthesizing {len(target_episodes)} specified episodes to {out_dir} (workers={args.workers})...")
        summary = synthesizer.synthesize_all(
            output_dir=out_dir,
            resolver=resolver,
            max_workers=args.workers,
            episode_numbers=target_episodes,
        )
        elapsed = time.time() - start_time
        print(f"Successfully generated {summary.total_episodes} notes ({summary.total_chapters} chapters) in {elapsed:.2f}s.")
        print(f"Chapter distribution: {dict(sorted(summary.chapter_distribution.items()))}")
    else:
        start_time = time.time()
        print(f"Synthesizing all {len(synthesizer.episode_numbers)} episodes to {out_dir} using {args.resolver} resolver (workers={args.workers})...")
        summary = synthesizer.synthesize_all(
            output_dir=out_dir,
            resolver=resolver,
            max_workers=args.workers,
        )
        elapsed = time.time() - start_time
        print(f"Successfully generated {summary.total_episodes} notes ({summary.total_chapters} chapters) in {elapsed:.2f}s.")
        print(f"Chapter distribution: {dict(sorted(summary.chapter_distribution.items()))}")


def cmd_audit(args: argparse.Namespace) -> None:
    synthesizer = EpisodeNoteSynthesizer()
    target_episodes = args.episodes if hasattr(args, "episodes") and args.episodes else None
    print("Auditing episodes for heading and takeaway defects...")
    result = synthesizer.audit(episode_numbers=target_episodes)
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
        print("All chapters pass 100% heading and takeaway quality engine validation!")


def cmd_diagnose(args: argparse.Namespace) -> None:
    excerpts = args.excerpts or []
    if args.heading:
        engine = HeadingQualityEngine()
        report = engine.diagnose(args.heading, excerpts, summary=args.summary or "")
        print(f"\nHeading: {args.heading}")
        print(f"Valid: {report.is_valid}")
        print(f"Diagnostics: {report.feedback_message}")
        if not report.is_valid and len(excerpts) >= 2:
            repaired = engine.repair(args.heading, excerpts, summary=args.summary or "")
            print(f"Deterministic repair: {repaired}")

    if args.takeaway:
        t_engine = TakeawayQualityEngine()
        t_report = t_engine.diagnose(args.takeaway, excerpts)
        print(f"\nTakeaway: {args.takeaway}")
        print(f"Valid: {t_report.is_valid}")
        print(f"Diagnostics: {t_report.feedback_message}")
        if not t_report.is_valid and len(excerpts) >= 1:
            t_repaired = t_engine.repair(args.takeaway, excerpts)
            print(f"Deterministic repair: {t_repaired}")


def cmd_doctor(args: argparse.Namespace) -> None:
    synthesizer = EpisodeNoteSynthesizer()
    repository = synthesizer.source_repository
    print("Running system doctor checks...")
    checks = [
        ("Channel index", synthesizer.channel_path.exists(), f"Found {repository.legacy_channel_count} entries"),
        ("Archive source", synthesizer.archive_path.exists(), f"Found {repository.legacy_archive_count} entries"),
        ("Transcripts dir", synthesizer.transcript_dir.exists(), f"Found {repository.legacy_transcript_count} transcripts"),
        (
            "Normalized snapshots",
            repository.invalid_snapshot_count == 0,
            f"Found {repository.normalized_snapshot_count} verified snapshots",
        ),
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


def cmd_topics(args: argparse.Namespace) -> None:
    from topic_synthesizer import (
        DEFAULT_TOPICS,
        TopicGuideSynthesizer,
        TopicQualityAuditor,
        load_all_notes_from_dir,
    )

    out_dir = args.out_dir or args.output_dir or OUTPUT_DIR
    topics_dir = out_dir / "topics"
    episodes_dir = out_dir / "episodes"

    if args.list:
        print("=== Gooaye 股癌 跨集數主題專題庫清單 ===")
        for idx, t in enumerate(DEFAULT_TOPICS, 1):
            print(f"{idx}. [{t.category}] {t.title} ({t.slug})")
            print(f"   關鍵字: {'、'.join(t.keywords[:8])}...")
            print(f"   簡介: {t.description}\n")
        return

    if args.generate:
        print(f"Loading episode notes from {episodes_dir}...")
        notes = load_all_notes_from_dir(episodes_dir)
        if not notes:
            print(f"❌ No episode notes found in {episodes_dir}. Please run 'synthesize' first.")
            sys.exit(1)

        selected_topics = DEFAULT_TOPICS
        if args.topic:
            selected_topics = tuple(t for t in DEFAULT_TOPICS if t.slug == args.topic)
            if not selected_topics:
                print(f"❌ Unknown topic slug: '{args.topic}'. Use 'topics --list' to see valid slugs.")
                sys.exit(1)

        print(f"Loaded {len(notes)} episode notes. Synthesizing {len(selected_topics)} topic guides to {topics_dir}...")
        start_time = time.time()
        syn = TopicGuideSynthesizer()
        files = syn.synthesize_and_save_all(notes, topics_dir, selected_topics)
        elapsed = time.time() - start_time
        print(f"✅ Successfully generated {len(files)} topic files in {elapsed:.2f}s:")
        for f in files:
            print(f"  - {f.name}")
        return

    if args.audit or not (args.list or args.generate):
        print(f"Auditing topic guides in {topics_dir} against {episodes_dir}...")
        auditor = TopicQualityAuditor()
        report = auditor.audit_all_topics(topics_dir=topics_dir, episodes_dir=episodes_dir)
        print(f"\nAudit completed: {report['total_topics']} topic guides audited.")
        print(f"Defect count: {report['defect_count']}")
        if report["defect_count"] > 0:
            print("\nDefects found:")
            for d in report["defects"]:
                print(f"  ❌ [{d.get('topic')}] ({d.get('category')}): {d.get('message')}")
            sys.exit(1)
        else:
            print("🎉 All topic guides pass 100% citation grounding and link validation!")



def main() -> None:
    parser = argparse.ArgumentParser(description="Gooaye Note Synthesis & Architecture Management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # download
    p_download = subparsers.add_parser(
        "download",
        help="Acquire one complete episode source snapshot",
    )
    selector = p_download.add_mutually_exclusive_group(required=True)
    selector.add_argument(
        "--episode",
        type=positive_episode_number,
        help="Acquire a specific positive episode number",
    )
    selector.add_argument(
        "--latest",
        action="store_true",
        help="Acquire the latest official episode; fail if its archive is pending",
    )
    p_download.add_argument(
        "--force",
        action="store_true",
        help="Replace changed local source content; identical content remains unchanged",
    )
    p_download.set_defaults(func=cmd_download)

    # synthesize
    p_syn = subparsers.add_parser("synthesize", help="Synthesize Markdown notes")
    p_syn.add_argument("--episode", type=int, help="Synthesize a single episode number")
    p_syn.add_argument("--episodes", type=int, nargs="+", help="Synthesize multiple episode numbers")
    p_syn.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Destination directory for notes")
    p_syn.add_argument("--out-dir", type=Path, default=None, help="Alias for --output-dir")
    p_syn.add_argument("--resolver", choices=["composite", "cache", "deterministic", "ollama"], default="composite", help="Heading resolution strategy")
    p_syn.add_argument("--workers", type=int, default=8, help="Number of worker threads for batch generation")
    p_syn.add_argument("--dry-run", action="store_true", help="Print markdown to stdout instead of writing to disk")
    p_syn.set_defaults(func=cmd_synthesize)

    # audit
    p_audit = subparsers.add_parser("audit", help="Audit heading and takeaway quality across the corpus")
    p_audit.add_argument("--episodes", type=int, nargs="+", help="Audit specific episode numbers")
    p_audit.set_defaults(func=cmd_audit)

    # diagnose
    p_diag = subparsers.add_parser("diagnose", help="Diagnose a specific heading or takeaway candidate")
    p_diag.add_argument("--heading", type=str, default=None, help="Heading candidate string")
    p_diag.add_argument("--takeaway", type=str, default=None, help="Takeaway candidate string")
    p_diag.add_argument("--excerpts", nargs="+", help="Chapter excerpt sentences")
    p_diag.add_argument("--summary", type=str, default="", help="Episode summary for leakage check")
    p_diag.set_defaults(func=cmd_diagnose)

    # doctor
    p_doc = subparsers.add_parser("doctor", help="Check integrity of system components and datasets")
    p_doc.set_defaults(func=cmd_doctor)

    # topics
    p_top = subparsers.add_parser("topics", help="Synthesize and audit thematic topic guides")
    p_top.add_argument("--generate", action="store_true", help="Batch synthesize all topic guides")
    p_top.add_argument("--audit", action="store_true", help="Audit grounding and links of all topic guides")
    p_top.add_argument("--list", action="store_true", help="List all defined topic guides")
    p_top.add_argument("--topic", type=str, default=None, help="Filter for a specific topic slug")
    p_top.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Base destination directory")
    p_top.add_argument("--out-dir", type=Path, default=None, help="Alias for --output-dir")
    p_top.set_defaults(func=cmd_topics)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
