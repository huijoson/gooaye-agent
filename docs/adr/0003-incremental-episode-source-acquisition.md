---
status: accepted
date: 2026-08-28
---

# Incremental episode source acquisition

Episode Acquisition produces one synthesis-ready Episode Source Snapshot without synthesizing notes or publishing the knowledge base. YouTube RSS is authoritative for episode identity, video ID, and original title; SoundOn RSS supplies publication time and duration for cross-checking; the non-official transcript archive supplies curated metadata and the Full Transcript. A missing or inconsistent source fails the acquisition instead of silently degrading or generating a replacement transcript.

New episodes are stored as self-contained, per-episode directories layered over the existing legacy snapshots. This keeps each change small and allows a fully validated directory to cross the commit boundary as one unit, while an Episode Source Repository hides the legacy/new layout from consumers. The first version is intentionally incremental and dependency-free: it supports existing local episodes and new episodes still present in the official feeds, but fails explicitly for an unknown episode outside the feed window rather than adding `yt-dlp` or accepting incomplete metadata.

Acquisition is idempotent when content hashes match. Changed upstream content requires explicit `--force`, replaces the current snapshot, and relies on Git for history. Default tests remain offline with source-faithful fixtures; an opt-in live contract test checks the upstream formats, and `/mnt/c` directory staging and replacement must pass a filesystem contract test before the feature is accepted.
