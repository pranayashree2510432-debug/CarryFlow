# CarryFlow — Beyond the Browser

CarryFlow is a local-first cross-website workflow demo. Its differentiator is a persistent **Workflow Passport**: versioned facts with provenance and permissions, semantic handoff receipts, conflict resolution, and recovery that reconciles saved actions with the destination page before continuing.

## Run locally

Requires Python 3.11+ and the packages in `requirements.txt`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```

Open http://127.0.0.1:8000. No API key is required. The mock reasoning mode uses deterministic semantic mappings. The three demo websites are served locally and use synthetic student data.

## Demo

1. Select **Start demo**. CarryFlow reads the source profile and creates a passport.
2. Open Portal A, review its handoff receipts, then fill the prepared application.
3. Open Portal B. Its qualification and completion-year labels differ; its location field is deliberately ambiguous. Inspect the receipts and fill the unambiguous fields.
4. Use **Introduce phone conflict** to version a changed phone number, then resolve it in the conflict card.
5. Use **Interrupt & resume**. CarryFlow reads the actual portal fields in the embedded page and compares them with the action ledger before deciding what remains.
6. The **Prepare submission** action creates a prepared receipt and waits for approval. No final submission occurs without approval.

To reset the synthetic demo, use **Reset demo**. Data is stored in `carryflow.db`.

## Development

```powershell
pytest
```

The test suite covers versions, provenance, semantic distinctions, conflicts, permissions, receipt creation, action idempotency, and recovery reconciliation.

## Scope and limitations

This hackathon MVP operates only on its three allowlisted local demo origins. Semantic interpretation is deterministic and rule-based in mock mode; it does not claim general natural-language browsing. The local browser preview is a real same-origin iframe, but the product does not attach to arbitrary third-party sessions. Site state reconciliation can verify visible form values and demo confirmation identifiers; external websites without idempotency support cannot guarantee exactly-once effects. Passwords, OTPs, and payment data are not modeled or stored.

See `docs/` for competitive research, product specification, innovation, architecture, security, and the demo script.
