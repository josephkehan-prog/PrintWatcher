---
name: update-documentation-file
description: Workflow command scaffold for update-documentation-file in PrintWatcher.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /update-documentation-file

Use this workflow when working on **update-documentation-file** in `PrintWatcher`.

## Goal

Update or correct an existing documentation file to reflect new information or fix errors.

## Common Files

- `CLAUDE.md`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Edit an existing documentation file (e.g., CLAUDE.md).
- Commit the changes with a 'docs:' prefix in the message.

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.