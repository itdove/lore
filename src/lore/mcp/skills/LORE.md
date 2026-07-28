# Lore Protocol

## When <lore-context> is present

The recall hook injects team knowledge into your context before each prompt.
When you see a `<lore-context>` block:

1. READ it before responding — it contains relevant team knowledge
2. APPLY it to your response — mention relevant findings naturally
3. CITE the entry key when referencing knowledge (e.g., "per bug:api:jwt-clock-skew")
4. DO NOT ignore it or ask questions already answered by the context
5. If the context contradicts your training data, prefer the team knowledge — it reflects real experience

## When to call query_knowledge explicitly

- User says "check lore", "ask lore", "search lore"
- No `<lore-context>` block was present but you suspect relevant knowledge exists
- You need knowledge on a different topic than what was recalled

Results are returned in relevance order (best match first).
Use limit=3 for targeted lookups, higher for broad exploration.

## When to store
Only store when the user explicitly asks:
- "store in lore", "save to lore", "add to lore"
- "remember this", "capture this decision"

Do NOT proactively call store_knowledge during normal conversation.
Knowledge from the session is automatically captured by the SessionEnd
hook — no manual storage needed unless the user requests it.

## When NOT to store
- Anything the user didn't ask you to store
- Current task state or ephemeral context
- Anything already in git history
- Obvious facts derivable from reading the code

## Key format
Colon-separated segments, 1 or more. Maps to file path: bug:api:jwt → bug/api/jwt.md
Examples: jwt-leeway, bug:jwt-expiry, bug:auth:jwt-expiry, decision:arch:polars-migration

## Tags
[bug, decision, pattern, convention, planned]

## Always include WHY
Bad:  "use snake_case"
Good: "use snake_case — matches Postgres schema naming"

## Level selection
When storing, choose the appropriate level:
- individual: personal preference or local discovery
- project: project-specific knowledge useful to any teammate on this project
- team: team-wide pattern or convention
- product: cross-repo architectural decision
- org: company-wide standard
Ask the user which level if uncertain.
