---
status: accepted
date: 2026-08-29
---

# Transactional knowledge-base publication

Only a complete corpus may become a formal Knowledge Base Publication; episode or topic subsets are isolated Previews. `KnowledgeBasePublisher.publish()` and `verify()` are the sole public lifecycle seam: the publisher builds one complete sibling staging tree from the same in-memory Episode Notes and Topic Guides, records every artifact in a SHA-256 Manifest, verifies the full graph, and then replaces the managed root under a destination-scoped fail-fast lock. This trades full rebuild time and roughly twice the publication space for one owner, deterministic completeness, rollback, and freedom from the current two-command ordering contract.

A destination may be empty, a valid Manifest-managed Publication, or a strictly recognizable legacy Publication. Unknown non-empty directories are rejected without a force bypass; failures preserve the previous complete root, and formal incremental publication remains intentionally unsupported.
