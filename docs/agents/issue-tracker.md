# Issue Tracker: GitHub Issues

Issues for this repository are tracked in GitHub Issues for `huijoson/gooaye-agent`.

---

## Tooling

Use the GitHub CLI (`gh`) to read, create, and manage issues:

- **List issues**: `gh issue list`
- **View an issue**: `gh issue view <number>`
- **Create an issue**: `gh issue create --title "<title>" --body "<body>"`
- **Edit issue labels**: `gh issue edit <number> --add-label "<label>"`
- **Close an issue**: `gh issue close <number>`

---

## Conventions

- **Ticket Titles**: Use clear, concise titles utilizing project domain terms.
- **Vertical Slices**: Each ticket created by agent skills (such as `to-tickets`) represents a full vertical slice and explicitly lists blocker ticket dependencies in its body.
- **Pull Requests**: Pull requests are not treated as triage request surfaces by default.
