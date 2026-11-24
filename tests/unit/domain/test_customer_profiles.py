import pytest

from app.domain.customer_profiles import validate_customer_profile


def test_manual_profile_has_no_access_account_and_email_is_optional():
    profile = validate_customer_profile(
        {"display_name": "Cliente Presencial", "phone": "987654321", "email": None},
        origin="MANUAL",
    )
    assert profile.origin == "MANUAL"
    assert profile.user_id is None
    assert profile.email is None


def test_portal_profile_requires_verified_account_reference():
    with pytest.raises(ValueError, match="cuenta"):
        validate_customer_profile(
            {"display_name": "Portal User", "phone": "987654321"}, origin="PORTAL"
        )


@pytest.mark.parametrize("values", [
    {"display_name": " ", "phone": "987654321"},
    {"display_name": "Cliente", "phone": "123"},
])
def test_profile_requires_nonempty_name_and_valid_phone(values):
    with pytest.raises(ValueError):
        validate_customer_profile(values, origin="MANUAL")


def test_duplicate_contact_values_are_not_rejected_or_merged():
    first = validate_customer_profile(
        {"display_name": "Cliente Uno", "phone": "987654321", "email": "same@example.com"}, origin="MANUAL"
    )
    second = validate_customer_profile(
        {"display_name": "Cliente Dos", "phone": "987654321", "email": "same@example.com"}, origin="MANUAL"
    )
    assert first.display_name != second.display_name
