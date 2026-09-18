---
status: accepted
date: 2026-09-18
---

# Cold transcript archive for permanent external preservation

To guard against the permanent loss of historical transcripts if upstream non-official archives (e.g. `whatmkreallysaid.com`) become unavailable, the repository maintains an independent root-level cold archive at `transcripts/` containing all 693 episodes (`EP0001.md` through `EP0693.md`) and an index `README.md`. Each file pairs standard YAML frontmatter (`episode`, `title`, `youtube_title`, `youtube_url`, `episode_date`, `duration`, `source`) with the verbatim, unpruned text of the episode.

This archive intentionally sits outside `.work/` (pipeline staging snapshots) and `gooaye-youtube-notes/` (transactional publication of distilled notes). Keeping verbatim transcripts in a dedicated root directory trades repository disk size for visibility, zero-tool human and agent readability, and decoupling from note distillation lifecycle rules. The acquisition workflow automatically updates this archive whenever a new episode source snapshot is acquired.
