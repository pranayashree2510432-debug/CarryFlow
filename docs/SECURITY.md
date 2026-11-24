# Security model

## Enforced in the demo

- Browser target is confined to three local pages; API transfer actions reject origins outside the local allowlist.
- Page content is untrusted data and has no path to alter the user goal, permissions, or execution policy.
- Fact permissions are checked server-side before filling.
- Unresolved conflicts and ambiguous fields are withheld.
- Final submission is separate from preparation and requires an explicit approval action.
- Duplicate action keys are persistent; verified, prepared, and uncertain actions are not blindly replayed.
- The demo never transmits data to an external service.
- Synthetic student data only; no passwords, OTPs, or payment credentials are stored.

## Limitations and production controls

The current UI and API are intended for a single local demo user, not deployment on a public network. Add authentication, CSRF protection, secure origin binding, rate limiting, database migrations, secrets management, encrypted sensitive values, audit retention controls, and a sandboxed Playwright worker before production. A malicious site can still exploit browser or model weaknesses; allowlisting, restricted actions, and approval reduce scope but cannot eliminate risk. A destination without idempotency support cannot provide exactly-once execution. Unknown outcomes must stay uncertain and require inspection or user action.
