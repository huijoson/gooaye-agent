---
name: setup-pstack
description: Configure project-local pstack model roles for Codex. Use for setup-pstack, pstack budget, or changing pstack model choices.
---

# Setup pstack for Codex

Read `.agents/vendor/pstack/docs/harness/codex.md` from the repository root.

1. Read `.agents/pstack-models.md` if it exists. Preserve existing role choices
   unless the user requested a change.
2. With no requested model choice, default all roles to `inherit-parent`.
   If the user requests model selection, inspect the actual spawn tool schema
   and present only models that it supports. Ask for a choice only when needed.
   Model overrides require the user's explicit selection. Model-family diversity
   is available only when distinct models are actually callable and selected.
3. Write `.agents/pstack-models.md` as Markdown with a `default: inherit-parent`
   line and any explicit per-role overrides. Role names are listed in
   `../poteto-mode/SKILL.md` and the upstream setup reference at
   `../../docs/harness/setup-pstack-cursor.md`. That reference describes Cursor;
   this workflow owns the Codex configuration location and defaults.
   Store requested effort as descriptive metadata only unless the tool schema
   and session instructions permit the explicit user-selected override.
4. Report the file written and the effective choices. State that this config
   is read by pstack workflows; it does not reconfigure Codex's parent model.
