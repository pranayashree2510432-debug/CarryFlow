# Architecture

## Runtime

- FastAPI serves the dashboard, three same-origin demo pages, and JSON API.
- SQLite stores versioned facts, workflow events, handoff receipts, conflicts, and action receipts.
- The dashboard uses a real iframe pointed at the local portal pages. It inspects and fills labeled local form controls, then reports observed values to the backend for verification.
- Deterministic semantic aliases make the demo reproducible without API credentials. `LLM_PROVIDER=mock` is the default; model configuration is reserved in `.env.example`.

## State flow

`PENDING → RUNNING → WAITING_FOR_USER / REQUIRES_RECONCILIATION → COMPLETED`

An action has its own lifecycle: `PREPARED → VERIFIED`, or `PREPARED → UNCERTAIN`; an inspected absent field can become `PENDING` for safe preparation. Final submission remains a prepared record until approval. The demo records a local confirmation and does not transmit data.

## Trust boundaries

- Only localhost demo origins are allowed.
- Website text is rendered as page content. It cannot update permissions, goal, or policy.
- The mapping layer proposes semantic matches; backend permission and conflict checks decide whether a value may be used.
- Browser observations are supplied from the same-origin iframe; the backend treats missing/uncertain observations conservatively.
- Passwords, OTPs, payment credentials, and raw browser cookies are not stored.

## Persistence model

`facts` retains versions by `(id, version)`. `receipts` records transfers. `actions` has a unique idempotency key. `conflicts` joins competing versions and their eventual resolution. `events` provides the timeline. `meta` stores workflow ID/status/current demo page.

For a production release, add schema migrations, user/workspace isolation, transaction-level uniqueness constraints for fact versions, authenticated API access, encrypted sensitive values, retention/deletion controls, and a real Playwright worker with a persistent browser context. The hackathon version keeps the controlled local workflow auditable with minimal dependencies.
