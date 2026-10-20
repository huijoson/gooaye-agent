# pstack model configuration

default: inherit-parent

All roles inherit the parent model. Omit model and reasoning overrides when
spawning agents.

This configuration is read by pstack workflows through the Codex adapter. It
does not reconfigure Codex's parent model.
