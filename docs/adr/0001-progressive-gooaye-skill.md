# ADR 0001: Progressive Gooaye Skill for Token-Efficient Knowledge Access

## Context & Problem Statement

This repository contains 689 episodes (540+ hours) of Gooaye (股癌) podcast transcripts and structured markdown notes. Users wish to leverage this extensive knowledge base to query historical market opinions and obtain investment mindset evaluations in Gooaye persona. 

However, loading massive prompts or maintaining an always-on heavy persona consumes substantial context window tokens and increases inference costs.

## Decision Drivers

1. **Token Efficiency**: Minimize idle system prompt token overhead and per-query consumption.
2. **Factual Grounding**: Ensure historical claims are anchored in verbatim transcript quotes rather than LLM hallucinations.
3. **Dual Interaction Modes**: Support both objective citation lookups and stylistic persona-based mindset reviews.
4. **Zero Extra Dependencies**: Rely on Antigravity's progressive skill architecture and standard file tools without requiring complex external vector databases.

## Considered Options

- **Option 1: Always-On Dedicated Persona Agent** (High token cost per turn, interferes with general programming tasks).
- **Option 2: Standalone Vector DB / Heavy RAG System** (Requires additional dependencies, embedding maintenance, and operational complexity).
- **Option 3: Progressive On-Demand Workspace Skill with Two-Stage Retrieval** (Selected).

## Decision Outcome

Adopt **Option 3**: Implement `.agents/skills/gooaye/SKILL.md` within the workspace root.

### Key Architectural Characteristics

1. **Progressive Disclosure**: The Skill exposes only a ~30 token metadata snippet to the system prompt; full instructions are loaded only when activated.
2. **Two-Stage Progressive Search**:
   - First stage checks `gooaye-youtube-notes/_index.md` or filters `episodes/` via filename/grep.
   - Second stage loads only the matched 1–3 `episodes/EPxxxx.md` files (~800–1,500 tokens).
   - Verbatim full transcripts in `.work/full-transcripts/` are kept on disk and queried only when deep context verification is required.
3. **Dual-Mode Response Logic**:
   - *Archive Queries*: Objective tone, strict date/episode/quote citation.
   - *Strategy / Mindset Queries*: Gooaye persona (pragmatic, anti-complacency, strict risk control, position sizing, cut-loss discipline).

## Consequences

### Positive
- Near-zero idle token cost.
- High accuracy with verified episode links.
- Version-controlled alongside the repository without external database dependencies.

### Negative / Trade-offs
- Deep semantic queries across hundreds of episodes rely on text pattern matching and structured headings rather than high-dimensional embedding similarity.
