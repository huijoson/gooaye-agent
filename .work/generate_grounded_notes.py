#!/usr/bin/env python3
"""Generate grounded Markdown notes from complete Gooaye transcripts using EpisodeNoteSynthesizer."""

from __future__ import annotations

import argparse
from pathlib import Path

from episode_synthesizer import EpisodeNoteSynthesizer, OUTPUT_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate grounded Markdown notes for Gooaye YouTube episodes")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Output directory for generated notes")
    args = parser.parse_args()

    synthesizer = EpisodeNoteSynthesizer()
    summary = synthesizer.synthesize_all(output_dir=args.output_dir)

    print(f"Generated {summary.total_episodes} grounded notes")
    print(f"Chapter distribution: {dict(sorted(summary.chapter_distribution.items()))}")
    all_nums = synthesizer.episode_numbers
    if all_nums:
        missing = sorted(set(range(min(all_nums), max(all_nums) + 1)) - set(all_nums))
        print(f"Missing public episode numbers: {missing}")


if __name__ == "__main__":
    main()
