"""Whether the application may rank what needs attention, and how far.

Ash's decision, 14 September 2026, answering the open question from the
interface concept: **the application may rank, as an indicative element only,
and that ranking goes nowhere else.**

Both halves matter and the second half is the load-bearing one. "May rank" on
its own would let an ordering become a score, a score become a field, and a
field become something a briefing carries to somebody else's desk. At that
point the application would be asserting a judgement it cannot source, which
is the one thing this codebase is built not to do.

So the decision is expressed here as a permission plus four boundaries, and
`tests/test_ranking_policy.py` enforces each rather than describing it:

● **A rank is computed for display and never stored.** It is not a field on a
  record, a claim, a segment or an assessment, and no migration adds one. An
  analyst's store holds what somebody asserted, not what the interface
  happened to sort by on a Tuesday.
● **A rank never leaves the screen.** It is absent from the briefing, from the
  comparison and from any export. A briefing already carries every statement's
  marker, confidence and source precisely so a reader can weigh it; a bare
  ordinal carries none of those and would read as an assessment.
● **A rank is not a claim and never wears a marker.** FACT, INFERENCE and
  SPECULATION describe how well something is evidenced. An ordering is not
  evidenced at all, it is a convenience, and dressing it in the provenance
  vocabulary would debase the vocabulary.
● **The ordering inputs must themselves be sourced.** Ranking is allowed to
  arrange facts the store already holds and already cites. It is not allowed
  to introduce a new judgement of its own, such as a threat score or a
  severity the sources do not state.

What this buys, in one line: an analyst gets a sensible starting order, and
nothing downstream can mistake that order for an assessment.
"""

from __future__ import annotations

DECIDED_ON = "2026-09-14"
DECIDED_BY = "Ash"

PERMITTED = "The application may order what needs attention, as an indicative aid."

# The four boundaries, in the words the interface shows. Served rather than
# copied into the markup, for the same reason the classification marking and
# the validation policy are: the rule an analyst reads and the rule the tests
# enforce have to come from one module.
BOUNDARIES = (
    "Indicative only. The order is a starting point, not an assessment.",
    "Never stored. No record, claim, segment or assessment carries a rank.",
    "Never exported. Briefings and comparisons carry no ordering.",
    "Never marked. A rank is not FACT, INFERENCE or SPECULATION.",
)

# The label the interface must show beside any ordered list, so the reader is
# told what the order is worth without having to know this module exists.
INDICATIVE_LABEL = "Indicative order"

# Field names a rank would arrive under. The guard tests refuse all of them
# anywhere in the store or an export, so a future implementation cannot leak
# one quietly under a plausible-looking name.
FORBIDDEN_FIELDS = frozenset(
    {
        "rank",
        "ranking",
        "priority",
        "score",
        "severity",
        "threat_score",
        "attention_score",
        "weight",
        "importance",
    }
)


def policy() -> dict[str, object]:
    """The rule, served so the interface cannot hold a different version."""
    return {
        "permitted": PERMITTED,
        "label": INDICATIVE_LABEL,
        "boundaries": list(BOUNDARIES),
        "decided_on": DECIDED_ON,
        "decided_by": DECIDED_BY,
        "caveat": (
            "An order is a convenience, not a judgement. It is computed for "
            "the screen, it is never written down, and it never travels."
        ),
    }
