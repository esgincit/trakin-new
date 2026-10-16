"""W-9 text parsing — pure functions, no database."""

from app.services.w9 import _classify_label, parse_w9_text

# Filled March-2024 W-9 whose section-1 label wraps mid-sentence across two lines
# ("... enter the business/disregarded" / "entity's name on line 2.)"). The wrap
# must not bleed into the legal name (used to parse as
# "entity's name on line 2.) DREP Software solution").
DREP_W9 = """Form W-9 (Rev. March 2024) Request for Taxpayer Identification Number and Certification
1 Name of entity/individual. An entry is required. (For a sole proprietor or disregarded entity, enter the owner's name on line 1, and enter the business/disregarded
entity's name on line 2.)
DREP Software solution
2 Business name/disregarded entity name, if different from above.
DREP Software solution
5 Address (number, street, and apt. or suite no.). See instructions.
16443 W ADAMS Street
6 City, state, and ZIP code
Goodyear, AZ 85338
Part I Taxpayer Identification Number (TIN)
Social security number
9 8 0 - 4 5 - 0 9 8 7
or
Employer identification number
3 4 - 6 7 7 5 4 3 2
Part II Certification
"""


def test_wrapped_section_label_does_not_bleed_into_legal_name():
    parsed = parse_w9_text(DREP_W9)
    assert parsed["legal_name"] == "DREP Software solution", parsed
    assert parsed["dba"] == "DREP Software solution", parsed
    assert parsed["address"] == "16443 W ADAMS Street", parsed
    assert (parsed["city"], parsed["state"], parsed["zip"]) == ("Goodyear", "AZ", "85338"), parsed
    assert parsed["tin"] in ("980-45-0987", "34-6775432"), parsed


def test_numeral_split_from_label_keeps_section_tracking():
    """IRS PDFs often put the margin numeral on its own text line ("1" / label).
    The numberless label must still open its section — the name must parse,
    and the label itself must never become the value."""
    text = ("Form W-9 (Rev. March 2024)\n"
            "1\n"
            "Name of entity/individual. An entry is required. (For a sole proprietor or disregarded "
            "entity, enter the owner's name on line 1, and enter the business/disregarded\n"
            "entity's name on line 2.)\n"
            "DREP Software solution\n"
            "2\n"
            "Business name/disregarded entity name, if different from above.\n"
            "DREP Software solution\n")
    parsed = parse_w9_text(text)
    assert parsed["legal_name"] == "DREP Software solution", parsed
    assert parsed["dba"] == "DREP Software solution", parsed


def test_line1_label_classifies_to_legal_name_despite_disregarded_mention():
    """The March-2024 line-1 label mentions "disregarded" — it must still map the
    line-1 widget to legal_name, never dba (which left legal_name empty)."""
    assert _classify_label("1 Name of entity/individual. An entry is required. (For a sole proprietor "
                           "or disregarded entity, enter the owner's name on line 1, and enter the business/disregarded") == "legal_name"
    assert _classify_label("entity's name on line 2.)") == "legal_name"
    assert _classify_label("2 Business name/disregarded entity name, if different from above.") == "dba"
    assert _classify_label("1 Name (as shown on your income tax return)") == "legal_name"
    assert _classify_label("5 Address (number, street, and apt. or suite no.). See instructions.") == "address"
    assert _classify_label("Social security number") == "ssn"
