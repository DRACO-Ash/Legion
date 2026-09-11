"""The provenance vocabulary, in words, served to the interface.

The interface must not hold its own copy of what FACT, INFERENCE and
SPECULATION mean. This project has now had four bugs where a message in the
browser described something the browser could not actually see, and a
hard-coded legend is the same shape of mistake: the words an analyst reads
about the epistemic status of a claim would drift from the rules the
validator enforces, and nothing would fail.

So the labels and the meanings live here, beside the validators that use the
same vocabulary, and `GET /api/provenance/legend` serves them. The interface
owns only the visual encoding, and even that is redundant by rule: colour and
icon and text, never colour alone.
"""

from __future__ import annotations

from typing import Any

from src.classification import DERIVED_SOURCE_CLASS, PUBLIC_SOURCE_CLASSES

# Order matters: strongest epistemic claim first, so the legend reads as a
# descending scale rather than an arbitrary list.
MARKERS: tuple[tuple[str, str, str], ...] = (
    (
        "FACT",
        "Fact",
        (
            "Stated directly by a named, citable public source. A fact with "
            "no citation is rejected rather than stored."
        ),
    ),
    (
        "INFERENCE",
        "Inference",
        (
            "Reasoned from cited facts. The reasoning is visible in the "
            "statement, and the conclusion is not itself in the source."
        ),
    ),
    (
        "SPECULATION",
        "Speculation",
        (
            "Conjecture that appears in the public literature, attributed to "
            "whoever is speculating. Never treat as established."
        ),
    ),
)

CONFIDENCE_LEVELS: tuple[tuple[str, str, str], ...] = (
    ("high", "High", "Corroborated by more than one independently read source."),
    (
        "moderate",
        "Moderate",
        "Rests on a single source, or on a source reporting another source.",
    ),
    ("low", "Low", "Weakly supported. Treat as a lead, not a finding."),
)

SOURCE_CLASS_LABELS: dict[str, str] = {
    "official_gov": "Official government",
    "peer_reviewed": "Peer reviewed",
    "think_tank": "Think tank",
    "commercial_ssa": "Commercial space domain awareness",
    "press": "Press",
    "catalogue": "Catalogue",
    "state_media": "State media",
    DERIVED_SOURCE_CLASS: "Internal assessment",
    "tbc": "TBC, re-verify",
}

# Source classes an analyst should read with extra caution, and why. Named
# rather than left to judgement, because analysts weight sources differently
# and the tool should say which way it is leaning.
SOURCE_CLASS_CAUTION: dict[str, str] = {
    "state_media": "The originating nation's own account of its own activity.",
    DERIVED_SOURCE_CLASS: (
        "Our own reasoning. It cites the public material it is derived from, "
        "which is what keeps this deployment open-source derived."
    ),
    "tbc": "Not yet sourced. Shown as unverified, never as established.",
}


def _entries(rows: tuple[tuple[str, str, str], ...]) -> list[dict[str, str]]:
    return [
        {"value": value, "label": label, "meaning": meaning}
        for value, label, meaning in rows
    ]


def legend() -> dict[str, Any]:
    """Everything the interface needs to explain a provenance chip."""
    return {
        "markers": _entries(MARKERS),
        "confidence_levels": _entries(CONFIDENCE_LEVELS),
        "source_classes": [
            {
                "value": value,
                "label": label,
                "public": value in PUBLIC_SOURCE_CLASSES,
                "caution": SOURCE_CLASS_CAUTION.get(value),
            }
            for value, label in SOURCE_CLASS_LABELS.items()
        ],
    }
