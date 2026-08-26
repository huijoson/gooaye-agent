# Domain Documentation

This repository follows a **single-context** domain documentation layout.

---

## Locations

- **Domain Model & Glossary**: [`CONTEXT.md`](../../CONTEXT.md) at the repository root (single source of truth for domain vocabulary and module interfaces).
- **Architectural Decision Records (ADRs)**: [`docs/adr/`](../adr/) (e.g., [`0001-progressive-gooaye-skill.md`](../adr/0001-progressive-gooaye-skill.md)).
- **Feature Specifications**: [`docs/specs/`](../specs/) (e.g., [`spec-gooaye-skill-and-knowledge-system.md`](../specs/spec-gooaye-skill-and-knowledge-system.md)).

---

## Consumer Rules for Agents

1. **Always read [`CONTEXT.md`](../../CONTEXT.md)** before planning, writing code, or generating tickets to adopt established domain terms (e.g., `EpisodeMetadata`, `ChapterEvidence`, `HeadingQualityEngine`).
2. **Consult [`docs/adr/`](../adr/)** when modifying or adding core architectural patterns (such as progressive skill disclosure or data synthesis pipelines).
3. **Keep documentation synchronized**: Update `CONTEXT.md` and ADRs whenever domain entities, quality rules, or architectural invariants change.
