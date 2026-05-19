import pytest
from app.schemas import LeadIn


def test_email_normalization():
    lead = LeadIn(email=" Ivan.Petrov@Acme.io ", message="Test")
    assert lead.email == "ivan.petrov@acme.io"


def test_email_empty_becomes_none():
    lead = LeadIn(email="   ", phone="0671234567", message="Test")
    assert lead.email is None


def test_phone_ua_10digit():
    lead = LeadIn(phone="0671234567", message="Test")
    assert lead.phone == "380671234567"


def test_phone_with_formatting():
    lead = LeadIn(phone="+38 (067) 123-45-67", message="Test")
    assert lead.phone == "380671234567"


def test_name_capitalization():
    lead = LeadIn(name="ivan PETROV", message="Test")
    assert lead.name == "Ivan Petrov"


def test_company_capitalization():
    lead = LeadIn(company="acme ua ltd", message="Test")
    assert lead.company == "Acme Ua Ltd"


def test_message_stripped():
    lead = LeadIn(message="  hello world  ", email="x@x.com")
    assert lead.message == "hello world"


def test_requires_contact_or_message():
    with pytest.raises(Exception):
        LeadIn(message="")


def test_minimal_valid_lead():
    lead = LeadIn(message="Цікавить реклама")
    assert lead.message == "Цікавить реклама"
    assert lead.source == "landing"
