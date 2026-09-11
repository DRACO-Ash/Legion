"""The SATCAT snapshot: the layout, and what it says about the catalogue.

The column offsets were measured against the supplied file rather than read
from a specification, so they are pinned here against real rows. A different
snapshot with a different shape has to fail loudly: a layout that slips by
one parses every row into plausible-looking nonsense.

The reconciliation tests matter more. A wrong catalogue number is the failure
nothing else in this application catches, because it plots a real satellite's
element sets under another satellite's name and every chart looks normal.
"""

from __future__ import annotations

import pytest

from src.candidate_systems import CANDIDATE_RECORDS
from src.satcat import iso_launch_date, launch_year, load_extract, parse_line
from src.satcat_reconcile import NAME, SHARED, reconcile
from src.seed_data import SEED_RECORDS

# Two real rows, copied from reference/satcat_26195.dat. The first is the
# oldest object in the file and the second is one of ours.
SPUTNIK_BOOSTER = (
    "1957-001A       1 SL-1 R/B                 CIS   04 OCT 57  TTMTR"
    "  01 DEC 57     96.19    65.10     938     214  4   20.4200 UHF"
)
SJ6_05A = (
    "2021-122A   49961 SHIJIAN 6 05A (SJ-6 05A) PRC   10 DEC 21  JSC  "
    "                96.03    97.41     570     567       2.2414 UHF"
)


# --- the layout -------------------------------------------------------------


def test_the_columns_land_where_they_were_measured() -> None:
    row = parse_line(SJ6_05A)
    assert row == {
        "intldes": "2021-122A",
        "norad_id": "49961",
        "name": "SHIJIAN 6 05A (SJ-6 05A)",
        "source": "PRC",
        "launch_date": "10 DEC 21",
        "launch_site": "JSC",
        "decay_date": "",
    }


def test_a_decayed_object_carries_its_decay_date() -> None:
    row = parse_line(SPUTNIK_BOOSTER)
    assert row["decay_date"] == "01 DEC 57"
    assert row["launch_site"] == "TTMTR"


@pytest.mark.parametrize("line", ["", "   ", "not a satcat row"])
def test_a_line_too_short_to_be_a_row_is_skipped(line: str) -> None:
    """Not a record of empty fields: an empty catalogue number would match
    nothing and read as an absent object rather than a broken file."""
    assert parse_line(line) is None


def test_the_two_digit_year_pivots_on_the_space_age() -> None:
    """Nothing was launched before 1957, so the pivot is exact for every row
    this file can hold rather than a guess about a window."""
    assert launch_year(parse_line(SPUTNIK_BOOSTER)) == 1957
    assert launch_year(parse_line(SJ6_05A)) == 2021
    assert iso_launch_date(parse_line(SJ6_05A)) == "2021-12-10"


# --- the shipped extract ----------------------------------------------------


def test_the_extract_covers_every_catalogue_number_we_reference() -> None:
    """The container ships the extract, not the 9 MB snapshot, so a gap here
    is a lookup that silently returns nothing in deployment."""
    snapshot = load_extract()
    referenced = {
        str(record["norad_id"])
        for record in [*SEED_RECORDS, *CANDIDATE_RECORDS]
        if record.get("norad_id")
    }
    assert referenced - set(snapshot) == set()


# --- the reconciliation -----------------------------------------------------


def test_a_number_claimed_by_more_than_one_record_is_reported() -> None:
    """At most one of them can be right, and until it is resolved two of the
    three plot a satellite that is not theirs."""
    report = reconcile([*SEED_RECORDS, *CANDIDATE_RECORDS])
    shared = [f for f in report["findings"] if f["kind"] == SHARED]

    assert shared == [
        {
            "kind": SHARED,
            "norad_id": "68762",
            "claimed_by": ["COSMOS-2612", "COSMOS-2613", "COSMOS-2614"],
        }
    ]


def test_the_snapshot_names_which_of_the_three_owns_that_number() -> None:
    """The finding is only useful if it says what the right answer is."""
    report = reconcile([*SEED_RECORDS, *CANDIDATE_RECORDS])
    named = {f["catalogue_name"]: f for f in report["findings"] if f["kind"] == NAME}

    assert set(named) == {"COSMOS-2613", "COSMOS-2614"}
    assert named["COSMOS-2613"]["satcat_name"] == "COSMOS 2612"


def test_a_house_abbreviation_is_not_a_discrepancy() -> None:
    """SJ for Shijian, SY for Shiyan, and a missing space in "Spacecraft2".
    A report full of non-discrepancies is a report nobody reads, and the real
    finding would be lost in it."""
    report = reconcile([*SEED_RECORDS, *CANDIDATE_RECORDS])
    names = {f.get("catalogue_name") for f in report["findings"]}

    assert "SY-12 01" not in names
    assert "SJ-6-05A" not in names
    assert "PRC Test Spacecraft 2" not in names


def test_an_unmatched_number_is_reported_rather_than_assumed_fine() -> None:
    report = reconcile([{"norad_id": "99999999", "catalogue_name": "Not real"}])
    assert report["findings"][0]["kind"] == "unknown"


def test_a_record_with_no_number_is_not_counted_as_checked() -> None:
    report = reconcile([{"norad_id": None, "catalogue_name": "No number"}])
    assert report["checked"] == 0
    assert report["findings"] == []
