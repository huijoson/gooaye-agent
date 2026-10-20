#!/usr/bin/env python3
"""Export cold transcript archive for permanent external preservation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".work"))

from cold_transcript_exporter import (  # noqa: E402
    export_all,
    export_episode,
    format_cold_transcript,
    render_readme_index,
    sync_cold_transcript,
    update_archive_index,
)
from episode_source_repository import EpisodeSourceRepository  # noqa: E402


def make_default_repository(root: Path) -> EpisodeSourceRepository:
    work_dir = root / ".work"
    return EpisodeSourceRepository(
        snapshot_root=work_dir / "episode-sources",
        legacy_channel_path=work_dir / "channel.json",
        legacy_archive_path=work_dir / "source" / "episodes.json",
        legacy_transcript_dir=work_dir / "full-transcripts",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Export all episodes (default)")
    parser.add_argument("--episode", type=int, help="Export a single episode number")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "transcripts",
        help="Target cold archive directory (default: transcripts/)",
    )
    args = parser.parse_args()

    repo = make_default_repository(ROOT)
    if args.episode:
        out = export_episode(args.episode, repo, args.output_dir)
        update_archive_index(repo, args.output_dir)
        print(f"Exported EP{args.episode:04d} to {out}")
    else:
        print(f"Exporting all {len(repo.episode_numbers)} episodes to {args.output_dir}...")
        total = export_all(repo, args.output_dir)
        print(f"Successfully exported {total} episodes and updated README.md in {args.output_dir}")


if __name__ == "__main__":
    main()
