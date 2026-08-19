---
name: kiro-steering
description: Maintain .kiro/steering/ as persistent project memory for this repository. Use when bootstrapping, inspecting, syncing, or updating Kiro steering documents, especially product.md, tech.md, structure.md, or custom steering files.
metadata:
  shared-rules: "rules/steering-principles.md"
---

# kiro-steering

## Role

Maintain `.kiro/steering/` as persistent project memory.

## Mission

- Bootstrap: generate core steering from the codebase the first time.
- Sync: keep steering and implementation aligned as the project changes.
- Preserve: user-authored steering is source material; update additively.

## Success Criteria

- Steering captures patterns and principles, not exhaustive file or dependency lists.
- Code drift is detected and reported.
- All `.kiro/steering/*.md` files are treated as project memory, including custom files.
- No secrets, credentials, or environment-specific private values are copied into steering.

## Required Reference

Read `rules/steering-principles.md` before creating or updating steering files.

## Scenario Detection

Inspect `.kiro/steering/`:

- Bootstrap mode: directory is empty or missing `product.md`, `tech.md`, or `structure.md`.
- Sync mode: all core files exist.

## Bootstrap Flow

1. Read templates from `.kiro/settings/templates/steering/` if present.
2. Analyze the codebase just in time:
   - Product: README, docs, package/dependency files, user-facing routes.
   - Tech: config files, dependencies, framework integration points.
   - Structure: directory layout, import patterns, naming conventions.
3. Extract durable patterns:
   - Product: purpose, value, core capabilities.
   - Tech: frameworks, runtime choices, conventions, architectural decisions.
   - Structure: module ownership, naming rules, import boundaries.
4. Generate the core steering files from the templates or from the same headings if templates are absent.
5. Summarize what was created and ask the user to treat the files as source of truth after review.

## Sync Flow

1. Read every file in `.kiro/steering/*.md`.
2. Analyze only the code and docs needed to check likely drift.
3. Compare both directions:
   - Steering -> code: documented pattern appears missing or changed; report as warning.
   - Code -> steering: new durable pattern; update candidate.
   - Custom steering: check whether specialized guidance remains relevant.
4. Update additively by default. Preserve existing sections and examples.
5. Add or update `_updated_at: YYYY-MM-DD_` when a file changes.
6. Report changed files, drift warnings, and recommendations.

## Granularity Rule

If new code follows existing patterns, steering should not need updating.

Prefer pattern statements with examples over file inventories.

Bad:

```markdown
- app/static/app.js - main chat UI
- app/static/admin.js - admin UI
- app/static/styles.css - shared styles
```

Good:

```markdown
### Frontend (`app/static/`)
Native HTML/CSS/JS single-page surfaces mounted by FastAPI. Keep shared visual language in
`styles.css`; avoid adding a frontend build step unless the product requirement justifies it.
```

## Codex Workflow Notes

- Use `rg`, `find`, and focused file reads before editing.
- Use patch-based edits for steering updates.
- Do not document `.codex/`, `.claude/`, `.kiro/settings/`, caches, generated output, or local data as project architecture.
- Mention uncertainty in the final report instead of guessing.
