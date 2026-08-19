# Steering Principles

Steering files are project memory, not exhaustive specifications.

## Content Granularity

### Golden Rule

> If new code follows existing patterns, steering should not need updating.

### Document

- Organizational patterns such as feature-first, layered, or domain-modular structure.
- Naming conventions.
- Import strategies.
- Architectural decisions.
- Durable technology standards.

### Avoid

- Complete file listings.
- Every component or dependency.
- Incidental implementation details.
- Agent-specific tooling directories such as `.cursor/`, `.gemini/`, `.claude/`, or `.codex/`.
- Detailed documentation of `.kiro/` metadata directories such as settings or automation.
- Generated outputs, caches, local databases, or secret-bearing files.

## Security

Never include:

- API keys, passwords, credentials.
- Database URLs, internal IPs, or tokens.
- Sensitive local data from `.env`, `data/`, logs, or generated artifacts.

## Quality Standards

- Single domain: one topic per file.
- Concrete examples: show patterns with representative paths or code snippets.
- Explain rationale: describe why decisions matter.
- Maintainable size: 100-200 lines is typical.

## Preservation

- Preserve user sections and custom examples.
- Add by default; replace only when clearly stale.
- Add or update `_updated_at: YYYY-MM-DD_`.
- Note why changes were made in the response to the user.

## File Focus

- `product.md`: purpose, value, business context, and stable capabilities.
- `tech.md`: key frameworks, standards, conventions, and decisions.
- `structure.md`: organization patterns, naming rules, ownership boundaries.
- Custom files: specialized patterns such as API, testing, security, deployment, or data workflows.
