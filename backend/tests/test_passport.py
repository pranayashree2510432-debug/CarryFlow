import pytest
from fastapi import HTTPException

from backend.app import main
from backend.app.passport import (
    FactCreateBody,
    FactUpdateBody,
    FactConfirmBody,
    FactPermissionsBody,
    add_or_version_fact,
    update_fact_value,
    confirm_fact_version,
    update_fact_permissions,
    list_passport_facts,
    validate_email,
    validate_phone,
)


@pytest.fixture(autouse=True)
def setup_db():
    main.init()
    main.reset()
    yield
    main.reset()


def test_add_new_profile_fact():
    with main.db() as c:
        res = add_or_version_fact(
            c,
            FactCreateBody(
                id="portfolio",
                label="Portfolio Website",
                value="https://aarav.dev.test",
                semantic_type="custom.portfolio",
                user_confirmed=True,
            ),
        )
        assert res["ok"] is True
        assert res["id"] == "portfolio"
        assert res["version"] == 1
        assert res["verification"] == "USER_CONFIRMED"
        assert res["user_confirmed"] == 1

        passport = list_passport_facts(c)
        assert any(item["active"]["id"] == "portfolio" for item in passport["passport"])


def test_edit_existing_fact_creates_new_version_and_preserves_history():
    main.start()  # Seeds 8 profile facts
    with main.db() as c:
        # Edit email
        res = update_fact_value(
            c,
            "email",
            FactUpdateBody(
                value="aarav.updated@example.test",
                source_label="Updated Contact Email",
                user_confirmed=True,
            ),
        )
        assert res["action"] == "created_new_version"
        assert res["version"] == 2

        # Check that both versions exist in database
        versions = c.execute("SELECT * FROM facts WHERE id='email' ORDER BY version ASC").fetchall()
        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[0]["value"] == "aarav.mehta@example.test"
        assert versions[1]["version"] == 2
        assert versions[1]["value"] == "aarav.updated@example.test"
        assert versions[1]["last_confirmed_at"] is not None


def test_validation_rejects_malformed_email_and_phone():
    with pytest.raises(HTTPException) as exc_email:
        validate_email("not-an-email-address")
    assert exc_email.value.status_code == 422

    with pytest.raises(HTTPException) as exc_phone_short:
        validate_phone("12345")  # Less than 7 digits
    assert exc_phone_short.value.status_code == 422

    with pytest.raises(HTTPException) as exc_phone_chars:
        validate_phone("phone-number-letters")
    assert exc_phone_chars.value.status_code == 422


def test_validation_prevents_address_semantic_confusion():
    with main.db() as c:
        # Cannot assign permanent semantic type to current_address
        with pytest.raises(HTTPException) as exc:
            add_or_version_fact(
                c,
                FactCreateBody(
                    id="current_address",
                    label="Current Address",
                    value="12 Lake View Road",
                    semantic_type="address.permanent",
                ),
            )
        assert exc.value.status_code == 422
        assert "Cannot assign permanent" in exc.value.detail


def test_confirm_fact_updates_status_and_timestamp():
    with main.db() as c:
        # Add an unconfirmed fact
        add_or_version_fact(
            c,
            FactCreateBody(
                id="skills",
                label="Technical Skills",
                value="Python, FastAPI, SQL, Docker",
                user_confirmed=False,
            ),
        )

        unconfirmed = c.execute("SELECT * FROM facts WHERE id='skills' ORDER BY version DESC LIMIT 1").fetchone()
        assert unconfirmed["user_confirmed"] == 0
        assert unconfirmed["verification"] == "UNVERIFIED"
        assert unconfirmed["last_confirmed_at"] is None

        # Confirm the fact
        conf_res = confirm_fact_version(c, "skills")
        assert conf_res["verification"] == "USER_CONFIRMED"
        assert conf_res["last_confirmed_at"] is not None

        confirmed = c.execute("SELECT * FROM facts WHERE id='skills' ORDER BY version DESC LIMIT 1").fetchone()
        assert confirmed["user_confirmed"] == 1
        assert confirmed["verification"] == "USER_CONFIRMED"


def test_unconfirmed_fact_is_prevented_from_automatic_sharing():
    main.start()
    with main.db() as c:
        # Add an unconfirmed degree update with a conflict
        add_or_version_fact(
            c,
            FactCreateBody(
                id="education",
                label="Degree",
                value="M.Tech Computer Science",
                user_confirmed=False,
                is_conflict=True,
            ),
        )

    # Prepare Portal A
    prep_a = main.prepare("a")
    degree_receipt = next(r for r in prep_a["receipts"] if r["destination_field"] == "academic_background")
    # Must NOT be proposed as an approved fill
    assert degree_receipt["status"] in {"WAITING_FOR_USER", "BLOCKED"}
    assert degree_receipt["permission"] == "REQUIRES_USER"

    # Fill Portal A
    fill_a = main.fill(main.FillBody(origin="http://127.0.0.1:8000/portal/a", observed={"academic_background": "M.Tech Computer Science"}))
    degree_action = next((a for a in fill_a["actions"] if "education" in a["idempotency_key"]), None)
    # Must NOT have run a verified fill
    assert degree_action is None or degree_action["status"] != "VERIFIED"


def test_origin_permission_restrictions_block_unauthorized_destinations():
    main.start()
    with main.db() as c:
        # Restrict phone sharing to only a non-existent external origin
        update_fact_permissions(
            c,
            "phone",
            FactPermissionsBody(permitted_origins=["http://exclusive-trusted-partner.test"]),
        )

    # Prepare Portal A (http://127.0.0.1:8000/portal/a)
    prep_a = main.prepare("a")
    phone_receipt = next(r for r in prep_a["receipts"] if r["destination_field"] == "phone")
    # Must be DENIED and BLOCKED because portal A is not in permitted_origins
    assert phone_receipt["permission"] == "DENIED"
    assert phone_receipt["status"] == "BLOCKED"

    # Fill attempt
    fill_a = main.fill(main.FillBody(origin="http://127.0.0.1:8000/portal/a", observed={"phone": "9876543210"}))
    phone_action = next((a for a in fill_a["actions"] if "phone" in a["idempotency_key"]), None)
    assert phone_action is None or phone_action["status"] != "VERIFIED"


def test_passport_endpoints_via_fastapi():
    main.start()
    # Test GET /api/passport
    passport_data = main.get_passport()
    assert passport_data["total_facts"] == 8
    assert len(passport_data["canonical_templates"]) >= 8

    # Test POST /api/passport/fact
    new_fact = main.create_passport_fact(
        FactCreateBody(
            id="github",
            label="GitHub Profile",
            value="https://github.com/aarav-mehta",
            user_confirmed=True,
        )
    )
    assert new_fact["id"] == "github"

    # Test PUT /api/passport/fact/github
    updated_fact = main.update_passport_fact(
        "github",
        FactUpdateBody(value="https://github.com/aarav-mehta-pro", user_confirmed=True),
    )
    assert updated_fact["version"] == 2

    # Test POST /api/passport/fact/github/permissions
    perm_res = main.update_passport_permissions(
        "github",
        FactPermissionsBody(permitted_origins=["http://127.0.0.1:8000"]),
    )
    assert perm_res["permitted_origins"] == ["http://127.0.0.1:8000"]
