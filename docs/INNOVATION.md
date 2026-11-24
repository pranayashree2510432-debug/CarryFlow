# Innovation: context integrity and continuity

## Defensible hypothesis

Browser control is widely available. CarryFlow tests whether a task can be made safer and more resumable by treating every transfer as a governed, version-aware event instead of retrieving a value from unstructured memory.

## Workflow Passport

The persisted passport is represented across relational tables: workflow metadata, versioned facts, event timeline, handoff receipts, conflicts, and action receipts. A fact has a semantic type, originating page/field, collection time, version, confidence, verification state, permitted origins, purpose, and confirmation status. Secrets are outside the model.

## Connected modules

### Semantic Handoff Receipts

Receipts explain the source field, destination field, semantic type, mapping rule, confidence, permission, and resulting verification. Ambiguous location is explicitly held because `Location` cannot distinguish current from permanent address.

### Context conflict intelligence

The demo adds a new phone version with a different value, marks it unverified, and presents both versions with their origins. Resolution marks the selected version as user-confirmed and retains the history. Downstream transfers skip unresolved conflicts.

### Reality-checked recovery

The dashboard sends the visible iframe form values to the recovery endpoint. The backend compares these observations with saved action statuses. Existing values are recognized; missing previously verified values become uncertain and require review. Recovery never triggers a form submission.

### Duplicate-action guard

Field actions use a stable key based on origin, destination field, fact ID, and fact version. Prepared, verified, or uncertain actions are not automatically repeated. A final submission is only prepared until the user approves it. The demo avoids claiming exactly-once semantics for real websites.

### Context drift

Fact versions make drift visible and preserve the older value. An update creates a conflict rather than silently overwriting the selected source. The version participates in the action key so new data cannot be confused with an earlier transfer.

## Why the combination matters

Provenance alone cannot tell whether an old value is still current. Freshness alone cannot tell where it may go. Permission alone cannot establish that a form accepted it. Recovery alone can still repeat an action if it lacks a ledger. CarryFlow joins these checks in a single auditable handoff and resume path.

## Current boundary

Semantic mapping is deterministic for the controlled demo vocabulary. Production would add a model-backed candidate mapper, but deterministic permission and state rules would remain authoritative. This MVP validates the interaction and persistence model; it does not prove general web mapping accuracy.
