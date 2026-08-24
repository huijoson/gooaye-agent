# Domain Documentation

This repository follows a **single-context** domain documentation layout.

---

## Locations

- **Domain Model & Glossary**: [`CONTEXT.md`](file:///Users/yuhan/coding/gooaye-agent/CONTEXT.md) at the repository root.
- **Architectural Decision Records (ADRs)**: [`docs/adr/`](file:///Users/yuhan/coding/gooaye-agent/docs/adr/) (e.g., [`0001-progressive-gooaye-skill.md`](file:///Users/yuhan/coding/gooaye-agent/docs/adr/0001-progressive-gooaye-skill.md)).

---

## Consumer Rules for Agents

1. **Always read [`CONTEXT.md`](file:///Users/yuhan/coding/gooaye-agent/CONTEXT.md)** before planning, writing code, or generating tickets to adopt established domain terms (e.g., `EpisodeMetadata`, `ChapterEvidence`, `HeadingQualityEngine`).
2. **Consult [`docs/adr/`](file:///Users/yuhan/coding/gooaye-agent/docs/adr/)** when modifying or adding core architectural patterns (such as progressive skill disclosure or data synthesis pipelines).
3. **Keep documentation synchronized**: Update `CONTEXT.md` and ADRs whenever domain entities, quality rules, or architectural invariants change.
