---
name: principle-guard-the-context-window
description: 'Apply when context is filling up: large outputs, long files, repeated reads, fan-out planning. Route bulk to subagents; keep summaries in the main thread, not raw payloads.'
---

Before following this skill in Codex, read `.agents/vendor/pstack/docs/harness/codex.md` from the repository root. Resolve this skill directory to its physical path before following relative references.

# Guard the Context Window

**Why:** Context overflow degrades reasoning quality, creates compression artifacts, and halts progress.

**Pattern:**
- **Size phases and cap scope.** Limit files per phase, set turn budgets, account for mechanism costs.
