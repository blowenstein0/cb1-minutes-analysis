"""Filename parsing tested against the REAL 138 hrefs scraped from nyc.gov."""

from datetime import date
from pathlib import Path

import pytest

from cb1.grouping import parse_href

FIXTURE = Path(__file__).parent / "fixtures" / "index_hrefs.txt"


# ---- date parsing: one case per real-world format ----

@pytest.mark.parametrize(
    "filename,expected_date,expected_ym",
    [
        ("jan2016.pdf", None, (2016, 1)),  # month-abbrev + year, no day
        ("minutes-202111.pdf", None, (2021, 11)),  # YYYYMM, no day
        ("minutes-20221109.pdf", date(2022, 11, 9), None),  # YYYYMMDD
        ("Combined-Public-Hearing-Board-Meeting-Minutes-10-13-16.pdf", date(2016, 10, 13), None),
        ("combined_ph_and__bd_minutes_2_15_17.pdf", date(2017, 2, 15), None),
        ("combined ph and bd mtg minutes 9_18_17.pdf", date(2017, 9, 18), None),
        (  # MDYYYY concatenated
            "combined_public_hearing_and_bd_meeting_minutes_292021_with_signatures_attachments_and_agenda.pdf",
            date(2021, 2, 9),
            None,
        ),
        (
            "Combined-Public-Hearing-Board-Meeting-Minutes-December-19-2023-full.pdf",
            date(2023, 12, 19),
            None,
        ),
        ("board_meeting_minutes_june_24_2020_with_attachments.pdf", date(2020, 6, 24), None),
        ("combined_public_hearing_and_board_meeting_minutes_9-8-2020_with_attachments.pdf", date(2020, 9, 8), None),
        ("03-12-24-Public-Hearing-Minutes.pdf", date(2024, 3, 12), None),
        ("Pages-from-Minutes-3.pdf", None, None),  # undated fragment
    ],
)
def test_date_parsing(filename, expected_date, expected_ym):
    ref = parse_href(f"/assets/brooklyncb1/downloads/pdf/{filename}")
    assert ref.date_guess == expected_date
    assert ref.year_month_guess == expected_ym


# ---- part + revised parsing ----

def test_explicit_part_numbers():
    r = parse_href("/x/Combined-Public-Hearing-Board-Meeting-Minutes-05-13-25-Part-1.pdf")
    assert (r.date_guess, r.part_no, r.is_revised) == (date(2025, 5, 13), 1, False)


def test_bare_trailing_part_number_after_date():
    r = parse_href(
        "/x/Pages-from-Combined-Public-Hearing-and-Board-Meeting-Minutes-12-10-24-2.pdf"
    )
    assert (r.date_guess, r.part_no) == (date(2024, 12, 10), 2)


def test_trailing_year_digit_is_not_a_part():
    r = parse_href("/x/Combined-Public-Hearing-Board-Meeting-Minutes-06-13-2023.pdf")
    assert r.part_no is None


def test_undated_fragment_keeps_part_number():
    r = parse_href("/x/Pages-from-Minutes-4.pdf")
    assert (r.date_guess, r.year_month_guess, r.part_no) == (None, None, 4)


@pytest.mark.parametrize(
    "filename",
    [
        "REVISED-Combined-Public-Hearing-Board-Meeting-Minutes-03-11-25.pdf",
        "combined_public_hearing_board_mtg_minutes_6_13_17_revised.pdf",
        "Combined-Public-Hearing-and-Board-Meeting-Minutes-6-7-22-rev.pdf",
        "Combined-Public-Hearing-Board-Meeting-Minutes-12-06-16-REVISED.pdf",
    ],
)
def test_revised_detection(filename):
    assert parse_href(f"/x/{filename}").is_revised


# ---- doc type hints ----

@pytest.mark.parametrize(
    "filename,hint",
    [
        ("Special-Meeting-Select-New-District-Manager-CB1-March-21-2023-Minutes.pdf", "special"),
        ("Special-Full-Board-Minutes-6-12-23.pdf", "special"),
        ("land_use_committee_held_ph_6_6_17_minutes.pdf", "committee"),
        ("Public-Hearing-Meeting-Minutes-01-20-26.pdf", "public_hearing"),
        ("Limited-Public-Hearing-Minutes-8-09-16.pdf", "public_hearing"),
        ("Combined-Public-Hearing-Board-Meeting-Minutes-02-10-26.pdf", "combined"),
        ("Combine_Public_Hearing_and_Board_Meeting_Minutes_2-8-22.pdf", "combined"),
        ("minutes-20221206.pdf", "unknown"),
    ],
)
def test_doc_type_hint(filename, hint):
    assert parse_href(f"/x/{filename}").doc_type_hint == hint


# ---- full-corpus invariants ----

def test_all_corpus_hrefs_parse():
    hrefs = [line.strip() for line in FIXTURE.read_text().splitlines() if line.strip()]
    assert len(hrefs) == 138
    refs = [parse_href(h) for h in hrefs]
    # the five undated fragments are the only files with no date hint at all;
    # the identify stage places them by page-1 content
    undated = sorted(
        r.filename for r in refs if not r.date_guess and not r.year_month_guess
    )
    assert undated == [f"Pages-from-Minutes-{i}.pdf" for i in range(1, 6)]
