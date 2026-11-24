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


def test_semantic_type_keeps_current_and_permanent_addresses_distinct():
    main.start()
    data = main.prepare("b")
    current = next(r for r in data["receipts"] if r["destination_field"] == "current_location")
    assert current["semantic_type"] == "address.current"
    assert current["source_field"] == "Current address"
    assert not any(r["source_field"] == "Permanent address" and r["destination_field"] == "current_location" for r in data["receipts"])
