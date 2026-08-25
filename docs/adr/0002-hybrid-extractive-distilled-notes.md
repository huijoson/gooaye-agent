# ADR 0002: Hybrid Extractive-Distilled Note Architecture with Two-Tier Progressive Storage

## Context & Problem Statement

The initial Gooaye note generation pipeline adopted a strictly extractive model (`content_method: "extractive_from_full_transcript"`). Under this model:
- Chapter count and boundaries were dictated by `split_seeds(summary)`, splitting third-party curated summary blurbs into 3–6 clauses.
- Each chapter hardcoded exactly two verbatim excerpts (`len(excerpts) == 2`).
- As a result, for a typical 50-minute episode (~18,000 CJK characters), notes contained only ~500–600 characters of body text (≈3% content coverage).
- Users found the content too thin, lacking structural topic granularity and missing high-level takeaway conclusions ("核心觀點").
- Furthermore, relying on third-party summary blurbs to dictate chapter count directly contradicted `CONTEXT.md` §3 ("僅作為主題檢索提示").

## Decision Drivers

1. **Information Depth & Granularity**: Scale chapter segmentation dynamically based on transcript semantic flow and duration (~6–10 chapters per 50-minute episode, including proper Q&A segmentation).
2. **High-Level Synthesis without Hallucination**: Provide a clear, distilled 1-sentence takeaway ("核心觀點") per chapter while preserving verbatim transcript excerpts as the indisputable factual anchor.
3. **Token Budget Preservation**: Keep the Progressive Skill's Stage 2 retrieval lightweight (~1k tokens) while allowing deep contextual inspection on demand.
4. **Autonomous Domain Truth**: Derive chapter boundaries and evidence solely from full transcripts, demoting third-party summaries to reference/hinting roles.

## Considered Options

- **Option 1: Pure Extractive Scaling**
  - Increase excerpts to 4–8 quotes and extract speaker verbatim sentences as takeaways.
  - *Drawbacks*: Speaker rarely speaks in clean, concise conclusion sentences; pure extraction fails to provide a cohesive high-level takeaway.
- **Option 2: Fully Generative Summarization**
  - Rewrite entire episodes into LLM-generated summaries and bullet points.
  - *Drawbacks*: Destroys the zero-hallucination moat; removes verbatim citations that make the knowledge base credible.
- **Option 3: Hybrid Extractive-Distilled Architecture with Two-Tier Storage** (Selected)
  - Chapter segmentation derived from transcript semantic flow.
  - Each chapter contains:
    - Distilled Chapter Heading (8–32 chars)
    - Distilled Chapter Takeaway (`**核心觀點：**`, 20–60 chars declarative judgment statement)
    - Verbatim Excerpts (`Chapter Evidence`, authentic quotes)
  - Two-tier storage layout:
    - `episodes/EPxxxx.md` (Slim navigation layer: Heading + 1-sentence Takeaway + 2 Core Excerpts, ~1k tokens).
    - `episodes/EPxxxx.full.md` (Deep contextual layer: Heading + Takeaway + 4–8 Expanded Excerpts + context).

## Decision Outcome

Adopt **Option 3**.

### Key Architectural Specifications

1. **Domain Model Extensions**:
   - `Chapter`: Enriched with `takeaway: str` and dynamic `excerpts: tuple[str, ...]`.
   - `content_method`: Changed from `extractive_from_full_transcript` to `hybrid_extractive_distilled`.
2. **Two-Tier Storage & Progressive Retrieval**:
   - **Stage 1**: Search `_index.md` (Episode title + Chapter headings, ~150KB total index).
   - **Stage 2**: Read matched `episodes/EPxxxx.md` (~1k tokens, fast navigation & mindset extraction).
   - **Stage 2.5 (Optional)**: Read matched `episodes/EPxxxx.full.md` for extended quote evidence and nuanced discussion flow.
   - **Stage 3 (Optional)**: Query raw `.work/full-transcripts/` for specific acoustic/transcription verification.
3. **Quality Gates**:
   - `HeadingQualityEngine`: Enforces 9 defect categories on headings.
   - `TakeawayQualityEngine`: Enforces declarative structure, non-trivial assertions, transcript entity grounding, and bans meta-filler ("主委在本段分享了/探討了").

## Consequences

### Positive
- Substantially richer coverage of podcast content (~6–10 chapters vs 3–5 chapters).
- Clear takeaway synthesis enables rapid comprehension while preserving authentic quotes.
- Progressive Skill token budget remains low for Stage 2 queries while unlocking high-depth lookups in Stage 2.5.
- Complies with `CONTEXT.md` §3 by removing third-party summary dependency for chaptering.

### Negative / Trade-offs
- Introducing generated takeaways requires LLM inference during synthesis and cache management for takeaways.
- Note storage footprint increases due to the dual-file (`.md` and `.full.md`) structure.
