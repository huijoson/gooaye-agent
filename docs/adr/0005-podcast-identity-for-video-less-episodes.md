---
status: accepted
date: 2026-09-09
---

# Podcast identity for episodes with no public video

ADR 0003 made YouTube RSS the sole authority for episode identity, video ID, and original title. EP232 shows that this is one authority too few: the episode is still published by the official SoundOn podcast feed and still has a Full Transcript in the archive, but it is absent from the channel's public video list, so it could never be acquired and was the only gap in an otherwise continuous EP1–EP693 corpus. Identity now resolves in order — YouTube RSS, then legacy channel metadata, then the official podcast feed — and the last tier is used only when the first two have nothing, producing a Video-less Episode.

A Video-less Episode is marked by an empty `youtube_id` and must carry an absolute `audio_url` pointing at its podcast page; its provenance records `audio_metadata` in place of `youtube_metadata`, and its note and index row render a SoundOn listen link plus an explicit statement that the channel no longer has a public video, rather than an empty YouTube URL. `audio_url` is written into a manifest only when it is non-empty, so every episode that still has a video keeps a byte-identical manifest and an unchanged content hash.

Two upstream guards were too strict to reach the episode and were narrowed rather than removed. Archive transcripts from the earlier era carry no `# EPnnn` heading, so the heading is now checked only when one is present, and a transcript without a heading is instead anchored by an archive filename that names the episode. The podcast feed's title/`itunes:episode` agreement is now checked on the entry that matches the request instead of on every entry scanned, because one mislabelled 2024 item (titled EP622, numbered 623) otherwise blocked every lookup older than itself; a contradiction in the matched entry still fails the acquisition.
