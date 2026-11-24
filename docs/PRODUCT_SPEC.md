# Product specification

## Product

CarryFlow prepares multi-website workflows while preserving the meaning and permission of each reused fact. The MVP focuses on a student preparing two internship applications from one source profile.

## User outcome

Prepare drafts on two independent portals without retyping the profile, inspect why each value was mapped, resolve changed data explicitly, and resume after interruption without replaying an uncertain action.

## Core loop

1. User starts a workflow with an explicit no-submit constraint.
2. CarryFlow records synthetic profile facts with source labels, version, verification, timestamp, and approved origins.
3. A portal form is inspected and mapped by semantic type.
4. Each eligible transfer creates a Handoff Receipt with source, target, reason, confidence, and permission.
5. Ambiguous fields are withheld. Conflicting versions require a user choice.
6. Field fill is recorded and verified against the actual embedded page.
7. Resume reads the current form and reconciles it with the action ledger.
8. Consequential final submission is a separate prepared action and requires explicit approval.

## MVP requirements

- Three independently styled local pages using synthetic data.
- Persistent SQLite passport, receipts, conflicts, events, and action ledger.
- Semantic aliases for different portal vocabulary and an explicit ambiguous location field.
- Version history with user resolution.
- Destination origin allowlist.
- Recovery endpoint receives observed visible form values before resume.
- Dashboard shows browser, progress, facts, receipts, conflicts, and actions.
- No external form submission.

## Success criteria

- All eight synthetic facts are persisted with source and permission metadata.
- Portal A/B mappings produce receipts; ambiguous location stays unfilled.
- A new phone version triggers a visible conflict without replacing the earlier one.
- Recovery accounts for actual page values and never replays final submission.
- Unauthorized origins are rejected.
- Prepared submission is distinct from approval.
- Automated tests assert the above invariants.

## Out of scope

Arbitrary third-party browsing, credential handling, CAPTCHA/MFA bypass, external submission, general-purpose LLM planning, production multi-user tenancy, and claims of exactly-once execution.
