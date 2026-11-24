import json
import pytest
from fastapi import HTTPException

from backend.app import main


def setup_function():
    main.startup()
    main.reset()


def test_versioned_facts_conflict_and_resolution_preserve_history():
    main.start()
    initial = main.state()
    assert len(initial["facts"]) == 8
    assert all(f["source_url"].endswith("/source") and f["permitted_origins"] for f in initial["facts"])
    conflict = main.conflict()
    assert len(conflict["conflicts"]) == 1
    assert {f["version"] for f in conflict["facts"] if f["id"] == "phone"} == {1, 2}
    main.resolve(main.ResolveBody(fact_id="phone", version=2))
    done = main.state()
    assert not done["conflicts"]
    assert len([f for f in done["facts"] if f["id"] == "phone"]) == 2
    assert next(f for f in done["facts"] if f["version"] == 2)["verification"] == "USER_CONFIRMED"


def test_semantic_handoffs_and_ambiguous_location_are_receipted():
    main.start()
    data = main.prepare("b")
    qualification = next(r for r in data["receipts"] if r["destination_field"] == "highest_qualification")
    assert qualification["semantic_type"] == "education.degree"
    assert qualification["source_field"] == "Degree"
    ambiguous = next(r for r in data["receipts"] if r["destination_field"] == "location")
    assert ambiguous["status"] == "WAITING_FOR_USER"
    assert ambiguous["permission"] == "REQUIRES_USER"


def test_fill_is_verified_and_recovery_checks_real_page_state_without_replay():
    main.start()
    main.prepare("a")
    values = {"candidate_name": "Aarav Mehta", "academic_background": "B.Tech Information Technology", "expected_completion": "2027", "technical_competencies": "Python, React, SQL", "contact_email": "aarav.mehta@example.test", "phone": "9876543210"}
    filled = main.fill(main.FillBody(origin="http://127.0.0.1:8000/portal/a", observed=values))
    assert len([a for a in filled["actions"] if a["status"] == "VERIFIED"]) == 6
    recovered = main.recover(main.FillBody(origin="http://127.0.0.1:8000/portal/a", observed=values))
    recovery = next(e for e in recovered["events"] if e["kind"] == "recovery")
    assert "6 verified actions already present" in recovery["detail"]
    assert all(a["status"] == "VERIFIED" for a in recovered["actions"])


def test_unknown_outcome_is_uncertain_and_not_replayed():
    main.start()
    main.prepare("a")
    main.fill(main.FillBody(origin="http://127.0.0.1:8000/portal/a", observed={}))
    state = main.recover(main.FillBody(origin="http://127.0.0.1:8000/portal/a", observed={"candidate_name": "Aarav Mehta"}))
    assert any(a["status"] == "UNCERTAIN" for a in state["actions"])
    again = main.fill(main.FillBody(origin="http://127.0.0.1:8000/portal/a", observed={}))
    assert any(a["status"] == "UNCERTAIN" for a in again["actions"])


def test_disallowed_origin_rejected_and_submit_requires_prepare_then_approval():
    with pytest.raises(HTTPException) as denied:
        main.fill(main.FillBody(origin="https://outside.example", observed={}))
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as not_ready:
        main.submit_approve()
    assert not_ready.value.status_code == 409
    prepared = main.submit_prepare()
    action = next(a for a in prepared["actions"] if a["action_type"] == "FINAL_SUBMISSION")
    assert action["status"] == "PREPARED"
    approved = main.submit_approve()
    action = next(a for a in approved["actions"] if a["action_type"] == "FINAL_SUBMISSION")
    assert action["status"] == "VERIFIED"
    assert "CF-DEMO-2048" in action["observed_result"]
    assert approved["meta"]["status"] == "COMPLETED"


def test_semantic_type_keeps_current_and_permanent_addresses_distinct():
    main.start()
    data = main.prepare("b")
    current = next(r for r in data["receipts"] if r["destination_field"] == "current_location")
    assert current["semantic_type"] == "address.current"
    assert current["source_field"] == "Current address"
    assert not any(r["source_field"] == "Permanent address" and r["destination_field"] == "current_location" for r in data["receipts"])


def test_resolve_keep_older_version_fills_chosen_version():
    main.start()
    # Introduce conflict on phone
    main.conflict()
    # User resolves by keeping v1 (older version)
    resolved = main.resolve(main.ResolveBody(fact_id="phone", version=1))
    assert not resolved["conflicts"]
    # Prepare portal A
    prepared = main.prepare("a")
    phone_receipt = next(r for r in prepared["receipts"] if r["destination_field"] == "phone")
    assert phone_receipt["source_version"] == 1
    # Fill portal A with observed v1 value
    filled = main.fill(main.FillBody(origin="http://127.0.0.1:8000/portal/a", observed={"phone": "9876543210"}))
    phone_action = next(a for a in filled["actions"] if "phone" in a["idempotency_key"])
    assert phone_action["status"] == "VERIFIED"


def test_multiple_conflicts_tracked_and_resolved_individually():
    main.start()
    # Introduce phone conflict (v1 vs v2)
    main.conflict()
    # Introduce a second conflict on email
    with main.db() as c:
        c.execute(
            "INSERT INTO facts(id, key, semantic_type, value, source_url, source_label, collected_at, version, confidence, verification, permitted_origins, purpose, user_confirmed) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("email", "email", "person.email", "aarav.work@example.test", "http://127.0.0.1:8000/portal/source", "Work email", main.NOW(), 2, 0.90, "UNVERIFIED_CONFLICT", json.dumps(sorted(main.ALLOWED)), "internship application", 0)
        )
        c.execute("INSERT INTO conflicts VALUES(?,?,?,?,0,NULL)", ("email-conflict-1", "email", 1, 2))
    
    st = main.state()
    assert len(st["conflicts"]) == 2
    conflict_fact_ids = {c["fact_id"] for c in st["conflicts"]}
    assert conflict_fact_ids == {"phone", "email"}

    # Resolve phone only
    main.resolve(main.ResolveBody(fact_id="phone", version=2))
    st = main.state()
    assert len(st["conflicts"]) == 1
    assert st["conflicts"][0]["fact_id"] == "email"

    # Resolve email
    main.resolve(main.ResolveBody(fact_id="email", version=1))
    st = main.state()
    assert len(st["conflicts"]) == 0


def test_full_demo_workflow_end_to_end():
    # 1. Start demo
    st = main.start(main.StartBody(user_goal="Prepare two internship applications using my profile. Do not submit anything without asking."))
    assert st["meta"]["status"] == "RUNNING"
    assert len(st["facts"]) == 8

    # 2. Portal A: prepare and fill
    prep_a = main.prepare("a")
    assert any(r["origin"].endswith("/portal/a") for r in prep_a["receipts"])
    a_values = {
        "candidate_name": "Aarav Mehta",
        "academic_background": "B.Tech Information Technology",
        "expected_completion": "2027",
        "technical_competencies": "Python, React, SQL",
        "contact_email": "aarav.mehta@example.test",
        "phone": "9876543210",
    }
    fill_a = main.fill(main.FillBody(origin="http://127.0.0.1:8000/portal/a", observed=a_values))
    assert len([a for a in fill_a["actions"] if a["status"] == "VERIFIED"]) == 6

    # 3. Portal B: prepare (verify ambiguous location is held)
    prep_b = main.prepare("b")
    ambiguous = next(r for r in prep_b["receipts"] if r["destination_field"] == "location")
    assert ambiguous["status"] == "WAITING_FOR_USER"

    # 4. Conflict: introduce phone conflict, resolve
    conf_st = main.conflict()
    assert len(conf_st["conflicts"]) == 1
    res_st = main.resolve(main.ResolveBody(fact_id="phone", version=2))
    assert len(res_st["conflicts"]) == 0

    # 5. Recovery check
    rec_st = main.recover(main.FillBody(origin="http://127.0.0.1:8000/portal/a", observed=a_values))
    assert rec_st["meta"]["status"] == "REQUIRES_RECONCILIATION"

    # 6. Two-step submission
    prep_sub = main.submit_prepare()
    sub_action = next(a for a in prep_sub["actions"] if a["action_type"] == "FINAL_SUBMISSION")
    assert sub_action["status"] == "PREPARED"

    appr_sub = main.submit_approve()
    sub_action_done = next(a for a in appr_sub["actions"] if a["action_type"] == "FINAL_SUBMISSION")
    assert sub_action_done["status"] == "VERIFIED"
    assert appr_sub["meta"]["status"] == "COMPLETED"
