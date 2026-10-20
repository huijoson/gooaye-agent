# pstack in Codex

This project installs pstack from `cursor/plugins` at commit
`88d47514b82e7c44f00f2b2a72ff6dd12158038c` with a local Codex adapter.
Read this adapter once per session before following a pstack workflow.
Session instructions and the user's authorized task scope govern execution.

## Skills and paths

The physical bundle root is `.agents/vendor/pstack/`. Public skill directories
under `.agents/skills/` are relative symlinks. Resolve symlinks before following
upstream relative links, including links to sibling skills, docs and agents.
Read a referenced skill's `SKILL.md` to run its workflow; a slash command in
upstream text means that read, not a shell command. User-facing Codex invocation
uses `$poteto-mode`, `$how`, etc. The upstream `tdd` and `teach` skills are exposed
as `$pstack-tdd` and `$pstack-teach`; the project's existing skills keep their names.
Within pstack workflows, those names refer to the bundled versions.

## Tools and delegation

Map `Read`, `Grep`, `Glob`, and `Bash` to available file/shell tools, using `rg`
for searches. Map `AskQuestion` to an available user-input tool. Use the session's
planning tool when present, otherwise maintain a short task list in progress updates.

Map `Task` to the session's collaboration/spawn tool when delegation is permitted.
The main chat runs the playbook. For `poteto-agent` and `comment-sicko`, read the
matching file under `agents/` and include its instructions and required file paths
in the worker's brief. Custom `subagent_type` names are instructions, not Codex
tool parameters. Use the available follow-up, message and wait tools for lifecycle
operations. Honor the concurrency limit and read-only briefs. Create a separate
git worktree when isolation is required. If delegation is unavailable, do the work
sequentially and report the missing independent review when relevant.

## Models and setup

Default every role to `inherit-parent`: omit model and reasoning overrides.
Cursor Grok/Claude model slugs do not identify models callable through Codex.
Read `.agents/pstack-models.md` when present for project-specific role choices;
only apply a model override explicitly selected by the user and supported by the
current tool schema. An inherited-model panel gives independent attempts, not
evidence from different model families. State that limitation when it matters.
Budget labels describe requested effort; they do not change the parent model or
its actual reasoning configuration.

For `$setup-pstack`, use the Codex-specific installed skill. Model configuration
belongs in `.agents/pstack-models.md`, read by this adapter, rather than Cursor
rules or global Codex configuration.

## Integrations

Use `gh` for GitHub operations within the authorized task. Treat Cursor
Automations, cloud-agent dashboards, and Bugbot provisioning as unavailable unless
the session actually supplies those integrations. Explain a skipped step briefly;
if it is required to prove the result, report the work as incomplete.
Existing Bugbot review comments can still be read and addressed through GitHub.

Discover actual local verification scripts and available browser tools for runtime
evidence. Optional `cursor-team-kit` skills (`deslop`, `control-cli`, `control-ui`)
are not bundled; inspect the diff and use available test or runtime tools for
the corresponding work. Map skill creation to available Codex skill-authoring
guidance. Read only this project's history when available; if Cursor transcript
paths or history tools are absent, use session context and report the limitation.
External communication and mutations follow session authorization, regardless of
the broader autonomy language in upstream skills.
