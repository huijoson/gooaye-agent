#!/usr/bin/env python3
"""Generate grounded Markdown notes from complete Gooaye transcripts using EpisodeNoteSynthesizer."""

from __future__ import annotations

import argparse
from pathlib import Path

from episode_synthesizer import (
    EpisodeNoteSynthesizer,
    PreviewOutputError,
    validate_preview_output_directory,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an isolated grounded-note Preview")
    parser.add_argument("--output-dir", type=Path, required=True, help="New or empty Preview directory")
    args = parser.parse_args()
    try:
        output_dir = validate_preview_output_directory(args.output_dir)
    except PreviewOutputError as error:
        parser.error(str(error))

    synthesizer = EpisodeNoteSynthesizer()
    summary = synthesizer.synthesize_all(output_dir=output_dir)

    print(f"Generated {summary.total_episodes} grounded notes")
    print(f"Chapter distribution: {dict(sorted(summary.chapter_distribution.items()))}")
    all_nums = synthesizer.episode_numbers
    if all_nums:
        missing = sorted(set(range(min(all_nums), max(all_nums) + 1)) - set(all_nums))
        print(f"Missing public episode numbers: {missing}")


if __name__ == "__main__":
    main()
