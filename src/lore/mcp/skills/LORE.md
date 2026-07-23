# Lore Protocol

## When to store
- After fixing a bug — root cause and fix pattern
- After an architectural decision — what and why
- After discovering a cross-session pattern
- Before ending session if something surprising happened

## When NOT to store
- Current task state or ephemeral context
- Anything already in git history
- Obvious facts derivable from reading the code

## Key format
Directory path in knowledge repo = key: type/domain/slug.md → type:domain:slug
Examples: bug/auth/jwt-expiry, decision/arch/polars-migration, convention/naming/snake-case

## Tags
[bug, decision, pattern, convention, planned]

## Always include WHY
Bad:  "use snake_case"
Good: "use snake_case — matches Postgres schema naming"

## Level selection
When storing, choose the appropriate level:
- individual: personal preference or local discovery
- team: team-wide pattern or convention
- product: cross-repo architectural decision
- org: company-wide standard
Ask the user which level if uncertain.
