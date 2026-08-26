# Agent Instructions

Welcome to the **gooaye-agent** codebase. This repository contains the Gooaye (股癌) knowledge base, data processing pipeline, and progressive agent skill.

---

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for `huijoson/gooaye-agent` using the `gh` CLI. See [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md).

### Triage labels

Canonical 5-role triage label vocabulary. See [`docs/agents/triage-labels.md`](docs/agents/triage-labels.md).

### Domain docs

Single-context layout with [`CONTEXT.md`](CONTEXT.md) and [`docs/adr/`](docs/adr/) at the repository root. See [`docs/agents/domain.md`](docs/agents/domain.md).

---

## Architecture & Conventions

1. **Domain Context**: Always consult [`CONTEXT.md`](CONTEXT.md) for domain glossary, deep module boundaries, and heading defect rules.
2. **Progressive Skill**: The agent skill is defined at [`.agents/skills/gooaye/SKILL.md`](.agents/skills/gooaye/SKILL.md). It operates with near-zero idle token cost and follows a two-stage retrieval protocol.
3. **Data Pipeline**: Core data extraction, heading quality validation, and synthesis code resides in `.work/`.
