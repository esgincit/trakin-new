"""W-9 text parsing — pure functions, no database."""

from app.services.w9 import parse_w9_text

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
