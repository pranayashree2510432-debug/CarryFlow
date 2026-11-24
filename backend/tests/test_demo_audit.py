import pytest
from backend.app import main


@pytest.fixture(autouse=True)
def setup_app():
    main.init()
    main.reset()
    yield
    main.reset()


def test_dashboard_and_portals_load_successfully():
    # 1. Main Dashboard
    html_home = main.home()
    assert "CarryFlow" in html_home
    assert "WORKFLOW PASSPORT" in html_home
    assert "LIVE BROWSER" in html_home
    assert "id=\"browser\"" in html_home

    # 2. Source Profile portal
    html_source = main.portal("source")
    assert "Student profile" in html_source
    assert "Aarav Mehta" in html_source

    # 3. Portal A
    html_a = main.portal("a")
    assert "Northstar Internships" in html_a
    assert "candidate_name" in html_a

    # 4. Portal B
    html_b = main.portal("b")
    assert "Summit Talent" in html_b
    assert "highest_qualification" in html_b


def test_complete_demo_workflow_audit():
    # STEP 1: Start CarryFlow
    st = main.start(main.StartBody(user_goal="Prepare two internship applications using my profile."))
    assert st["meta"]["status"] == "RUNNING"
    assert len(st["facts"]) == 8
    assert all(f["verification"] == "VERIFIED" for f in st["facts"])

    # STEP 2: Navigate to Portal A & Prepare
    prep_a = main.prepare("a")
    receipts_a = [r for r in prep_a["receipts"] if r["origin"].endswith("/portal/a")]
    assert len(receipts_a) == 6

    # STEP 3: Inspect field mappings and confidence for Portal A
    expected_a = {
        "candidate_name": ("person.name", "Aarav Mehta"),
        "academic_background": ("education.degree", "B.Tech Information Technology"),
        "expected_completion": ("education.graduation_year", "2027"),
        "technical_competencies": ("skills.technical", "Python, React, SQL"),
        "contact_email": ("person.email", "aarav.mehta@example.test"),
        "phone": ("person.phone", "9876543210"),
    }
    for r in receipts_a:
        dest = r["destination_field"]
        assert dest in expected_a
        exp_sem, _ = expected_a[dest]
        assert r["semantic_type"] == exp_sem
        assert r["confidence"] >= 0.90
        assert r["status"] == "PROPOSED"
        assert r["permission"] == "APPROVED"
        assert "mapped from verified profile field" in r["reason"]

    # STEP 4: Fill approved fields for Portal A
    observed_a = {k: val for k, (_, val) in expected_a.items()}
    fill_a = main.fill(main.FillBody(origin="http://127.0.0.1:8000/portal/a", observed=observed_a))
    verified_actions_a = [a for a in fill_a["actions"] if a["status"] == "VERIFIED" and a["origin"].endswith("/portal/a")]
    assert len(verified_actions_a) == 6

    # STEP 5: Navigate to Portal B & Prepare
    prep_b = main.prepare("b")
    receipts_b = [r for r in prep_b["receipts"] if r["origin"].endswith("/portal/b")]
    assert len(receipts_b) == 6

    # STEP 6: Verify that differently worded fields map correctly on Portal B
    # Portal B has different terminology:
    # "applicant_name" -> person.name
    # "highest_qualification" -> education.degree
    # "passing_year" -> education.graduation_year
    # "core_competencies" -> skills.technical
    # "current_location" -> address.current
    mapped_b = {r["destination_field"]: r for r in receipts_b}

    assert mapped_b["applicant_name"]["semantic_type"] == "person.name"
    assert mapped_b["applicant_name"]["status"] == "PROPOSED"
    assert mapped_b["applicant_name"]["confidence"] >= 0.90

    assert mapped_b["highest_qualification"]["semantic_type"] == "education.degree"
    assert mapped_b["highest_qualification"]["source_field"] == "Degree"
    assert mapped_b["highest_qualification"]["status"] == "PROPOSED"

    assert mapped_b["passing_year"]["semantic_type"] == "education.graduation_year"
    assert mapped_b["passing_year"]["status"] == "PROPOSED"

    assert mapped_b["core_competencies"]["semantic_type"] == "skills.technical"
    assert mapped_b["core_competencies"]["status"] == "PROPOSED"

    assert mapped_b["current_location"]["semantic_type"] == "address.current"
    assert mapped_b["current_location"]["source_field"] == "Current address"
    assert mapped_b["current_location"]["status"] == "PROPOSED"

    # STEP 7: Test the ambiguous address field on Portal B
    # Portal B has "location" (generic without current/permanent distinction)
    ambiguous_receipt = mapped_b["location"]
    assert ambiguous_receipt["semantic_type"] == "address.unknown"
    assert ambiguous_receipt["status"] == "WAITING_FOR_USER"
    assert ambiguous_receipt["permission"] == "REQUIRES_USER"
    assert ambiguous_receipt["mapping_type"] == "AMBIGUOUS"
    assert ambiguous_receipt["confidence"] <= 0.50
    assert ambiguous_receipt["source_field"] == "Unresolved location"
    assert "ambiguous" in ambiguous_receipt["reason"].lower()

    # STEP 8: Fill Portal B and ensure ambiguous field is NOT filled
    observed_b = {
        "applicant_name": "Aarav Mehta",
        "highest_qualification": "B.Tech Information Technology",
        "passing_year": "2027",
        "core_competencies": "Python, React, SQL",
        "current_location": "12 Lake View Road, Bengaluru",
        "location": "",  # Ambiguous field remains empty
    }
    fill_b = main.fill(main.FillBody(origin="http://127.0.0.1:8000/portal/b", observed=observed_b))
    verified_actions_b = [a for a in fill_b["actions"] if a["status"] == "VERIFIED" and a["origin"].endswith("/portal/b")]
    assert len(verified_actions_b) == 5

    # Location must have NO action created, or must not be verified
    location_action = next((a for a in fill_b["actions"] if "location" in a["idempotency_key"] and "current_location" not in a["idempotency_key"]), None)
    assert location_action is None or location_action["status"] != "VERIFIED"
