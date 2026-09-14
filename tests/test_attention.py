"""The attention queue: sourced inputs, an indicative order, and nothing more.

Ash's decision, 14 September 2026. `tests/test_ranking_policy.py` guards the
boundaries against the rest of the application; this file checks that the
queue itself obeys them and, just as importantly, that it is not silently
empty.

A queue built on a field name that does not exist passes every boundary test
ever written, because an empty list carries no rank, reaches no store and
appears in no briefing. Three of this module's shapes were guessed wrong at
first and each guess produced exactly that: object `claims` are empty because
claims are analyst-created, the collection is `pol_segments` and not
`segments`, and TBC is a `source_class` and not a marker.
"""

from __future__ import annotations

from src.attention import (
    CATEGORY_ORDER,
    OFF_PLOT,
    OPEN_BEHAVIOUR,
    UNSIGNED,
    UNVERIFIED,
)
from src.ranking_policy import FORBIDDEN_FIELDS, INDICATIVE_LABEL


def _queue(client) -> dict:
    response = client.get("/api/attention")
    assert response.status_code == 200, response.json()
    return response.json()


def test_the_queue_is_not_empty_against_the_seeded_catalogue(client):
    """The test that would have caught every shape I guessed wrong.

    An empty queue satisfies every other check in this file and in the policy
    guards, so the first thing to assert is that the thing found anything at
    all, from more than one category.
    """
    queue = _queue(client)

    assert queue["count"] > 0, "the queue found nothing in a fully seeded store"
    populated = [row for row in queue["categories"] if row["count"] > 0]
    assert len(populated) >= 2, f"only one category ever fires: {queue['categories']}"


def test_every_category_that_fires_is_one_the_store_can_evidence(client):
    """No category outside the declared set, and the set is the stated order."""
    queue = _queue(client)

    assert [row["name"] for row in queue["categories"]] == list(CATEGORY_ORDER)
    assert {entry["category"] for entry in queue["entries"]} <= set(CATEGORY_ORDER)


def test_entries_are_grouped_in_the_stated_order(client):
    """The order is the category order, and the category is printed.

    That is the whole of the ranking: a reader can disagree with it without
    having to guess what produced it.
    """
    queue = _queue(client)
    positions = [CATEGORY_ORDER.index(entry["category"]) for entry in queue["entries"]]
    assert positions == sorted(positions)


def test_a_family_is_named_not_slugged(client):
    """A reader sees "Shenlong", never "chn-shenlong".

    Assessment records carry `family_id` and no title, so the first version of
    this queue printed the internal key. Showing a slug is the same defect as
    rendering a raw uuid, which this interface has been caught doing twice.
    """
    queue = _queue(client)
    family_entries = [
        entry
        for entry in queue["entries"]
        if str(entry["subject_id"]).startswith("family:")
    ]
    assert family_entries, "no family entries to check"
    for entry in family_entries:
        slug = str(entry["subject_id"]).removeprefix("family:")
        assert entry["subject"] != slug, f"printed the slug: {entry['subject']}"


def test_an_unverified_entry_names_who_must_verify_it(client):
    """A TBC with no owner is rejected at the model. The queue shows the owner."""
    queue = _queue(client)
    unverified = [e for e in queue["entries"] if e["category"] == UNVERIFIED]
    assert unverified, "no unverified entries in a store with TBC assessments"
    assert all(entry["detail"].strip() for entry in unverified)


def test_an_open_behaviour_is_never_called_ongoing(client):
    """A missing end is "no recorded end", never "ongoing".

    A blank field is not evidence of continuation. Where a source does say a
    behaviour continues, as for COSMOS-2558, the claim says so and the claim
    is what is shown.
    """
    queue = _queue(client)
    assert OPEN_BEHAVIOUR in [row["name"] for row in queue["categories"]]
    assert "ongoing" not in OPEN_BEHAVIOUR.lower()

    open_rows = [e for e in queue["entries"] if e["category"] == OPEN_BEHAVIOUR]
    for entry in open_rows:
        assert entry["subject"], "an open behaviour with no subject"


def test_the_queue_carries_the_policy_that_limits_it(client):
    """A caller cannot show the order without the words that qualify it."""
    queue = _queue(client)

    assert queue["label"] == INDICATIVE_LABEL
    assert len(queue["policy"]["boundaries"]) == 4
    assert queue["policy"]["decided_by"] == "Ash"


def test_the_queue_carries_no_score_of_its_own(client):
    """The ordering is categorical. There is no number to argue with.

    A score would be a judgement this application formed, which is the one
    thing the fourth boundary forbids.
    """
    queue = _queue(client)
    keys = {key for entry in queue["entries"] for key in entry}
    leaked = keys & (FORBIDDEN_FIELDS - {"rank"})
    assert leaked == set(), f"the queue invented a score: {leaked}"
    assert all(isinstance(entry.get("category"), str) for entry in queue["entries"])


def test_an_off_plot_entry_appears_only_when_something_lacks_a_number(client):
    """The seeded catalogue gives all seven candidates real identities.

    So this category is legitimately empty today, and the test says that
    rather than asserting a count nobody can explain later. If a record ever
    loses its NORAD id, the category fires and this still holds.
    """
    queue = _queue(client)
    counts = {row["name"]: row["count"] for row in queue["categories"]}
    systems = client.get("/api/systems").json()["systems"]
    without = [r for r in systems if not r.get("norad_id") and not r.get("archived")]

    assert counts[OFF_PLOT] == len(without)


def test_the_shown_count_never_overstates_what_was_returned(client):
    """`shown` is what the caller got, `count` is what exists.

    An interface that prints "14" beside a list of 14 while 52 wait unseen is
    lying by omission, so both numbers are served.
    """
    queue = _queue(client)

    assert queue["shown"] == len(queue["entries"])
    assert queue["shown"] <= queue["count"]
    assert queue["count"] == sum(row["count"] for row in queue["categories"])


def test_unsigned_is_every_family_that_has_not_been_signed(client):
    """Cross-checked against the families endpoint rather than a fixed number."""
    queue = _queue(client)
    counts = {row["name"]: row["count"] for row in queue["categories"]}
    families = client.get("/api/families").json()["families"]
    awaiting = [f for f in families if f.get("awaiting_validation")]

    assert counts[UNSIGNED] == len(awaiting)


def test_every_populated_category_is_reachable(client):
    """A strict prefix hid two whole categories.

    With seventeen unverified and fifteen unsigned, the first fourteen entries
    were all assessments, so the twenty open behaviours were unreachable while
    the category counts told the analyst they were there. Found by driving the
    page, not by reading the code.
    """
    queue = _queue(client)
    populated = {row["name"] for row in queue["categories"] if row["count"] > 0}
    shown = {entry["category"] for entry in queue["entries"]}

    assert populated <= shown, f"unreachable from the queue: {populated - shown}"
