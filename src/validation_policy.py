"""Who may sign off a family assessment.

Ash's decision, 14 September 2026, answering [DECISION - Ash] item 3: **any
member of the DOK team may sign one off.** That is the whole policy, and it
is recorded here rather than left in a chat message so the next person can
find it.

What this module does and does not do is worth stating plainly, because the
gap is a real one and hiding it would be worse than having it.

● **It records an assertion, it does not authenticate one.** There is no
  application-level authentication and that was a decision, so the name a
  signer types is the whole of the record, exactly as `asserted_by` is on
  every claim. Nothing here can tell whether the person typing is on the DOK
  team, and nothing here pretends to.
● **A sign-off therefore names a person and states the entitlement.** Not a
  tick, not a boolean, not "validated: true". A reader of an assessment
  months later needs to know who stood behind it and under what authority,
  and the string this module builds carries both.
● **The entitlement is stored beside the name**, so if the policy widens or
  narrows later, old sign-offs still say which rule they were made under.

If a sign-off ever needs to be provably restricted to the DOK team rather
than asserted, that needs identity from the platform, the same conclusion the
team token reached in 0.9.0.
"""

from __future__ import annotations

ENTITLED_TEAM = "DOK"
ENTITLEMENT = (
    f"Any member of the {ENTITLED_TEAM} team may sign off a family assessment."
)
DECIDED_ON = "2026-09-14"
DECIDED_BY = "Ash"

NAME_REQUIRED = (
    "Name whoever is signing this off. There is no authentication here, so "
    "the name is the whole of the record, and whitespace is a validation by "
    "nobody."
)


def policy() -> dict[str, str]:
    """The rule, served so the interface cannot hold a different version."""
    return {
        "team": ENTITLED_TEAM,
        "entitlement": ENTITLEMENT,
        "decided_on": DECIDED_ON,
        "decided_by": DECIDED_BY,
        "caveat": (
            "Recorded, not authenticated. The signer's name is asserted, in "
            "the same way every claim's asserted_by is."
        ),
    }


def signature(name: str) -> dict[str, str]:
    """One sign-off: who, under what entitlement, as at when.

    The entitlement is stored with the name rather than looked up later, so
    a sign-off made today still states the rule it was made under if the
    policy changes.
    """
    return {
        "validated_by": name.strip(),
        "validated_entitlement": ENTITLEMENT,
        "validated_team": ENTITLED_TEAM,
    }
