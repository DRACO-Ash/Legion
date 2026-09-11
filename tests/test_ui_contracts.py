"""Contracts the single-file admin UI has to keep.

The UI is vanilla JavaScript with no test runner of its own, so these assert
on its source from Python. They cover the two things that break silently: a
route renamed on the server while the UI still calls the old path, and a
catalogue value interpolated into markup without escaping.
"""

from __future__ import annotations

import pathlib
import re

from src.app import build_app

from .conftest import FakeUDLClient, make_settings

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX_HTML = (ROOT / "src" / "static" / "index.html").read_text(encoding="utf-8")

# The validated dark palette, in the order the validator was run on. The order
# is the colour-vision-deficiency safety mechanism, so a reorder is a change
# that has to be re-validated, not a tidy-up.
SERIES_PALETTE = [
    "#3987e5",
    "#d95926",
    "#199e70",
    "#c98500",
    "#d55181",
    "#008300",
    "#9085e9",
    "#e66767",
]

SORTABLE_COLUMNS = [
    "catalogue_name",
    "nation",
    "regime",
    "launch_year",
    "status",
    "norad_id",
]


def _placeholder(path: str) -> str:
    """Reduce both a JS template slot and a FastAPI path parameter to one form."""
    return re.sub(r"\{[^}]*\}", "{}", path.replace("${", "{"))


def test_every_path_the_ui_calls_exists_on_the_server() -> None:
    """A renamed route would otherwise fail only in a browser, at runtime.

    The OpenAPI schema is the app's own statement of what it serves, so this
    compares the UI against the contract rather than against route internals.
    """
    app = build_app(settings=make_settings(), udl_client=FakeUDLClient())
    served = {_placeholder(path) for path in app.openapi()["paths"]}
    called = {
        _placeholder(match)
        for match in re.findall(r"""fetch\(["'`]([^"'`?]+)""", INDEX_HTML)
    }
    assert called, "The UI should be calling the API"
    assert called <= served, (
        f"UI calls paths the server does not serve: {called - served}"
    )


def test_every_sortable_column_is_a_real_record_field() -> None:
    for key in SORTABLE_COLUMNS:
        assert f'{{key:"{key}"' in INDEX_HTML.replace(" ", "")


def test_sorting_is_announced_to_assistive_technology() -> None:
    assert "aria-sort" in INDEX_HTML
    assert "data-sort=" in INDEX_HTML


def test_catalogue_values_are_escaped_before_they_reach_the_markup() -> None:
    """Catalogue names are analyst-entered. Interpolating one raw into
    innerHTML is stored cross-site scripting."""
    raw = re.findall(r"\$\{s\.(\w+)\}", INDEX_HTML)
    assert raw == [], f"Interpolated without esc(): {raw}"


def test_the_series_palette_is_the_validated_one() -> None:
    declared = re.findall(r"--series-\d:(#[0-9a-f]{6})", INDEX_HTML)
    assert declared == SERIES_PALETTE


def test_the_palette_is_never_cycled_past_its_slots() -> None:
    """A ninth colour would be indistinguishable from one already plotted."""
    assert "SERIES_SLOTS = 8" in INDEX_HTML
    assert "MAX_SERIES = 8" in (ROOT / "src" / "family_elements.py").read_text(
        encoding="utf-8"
    )


def test_each_chart_carries_a_table_view() -> None:
    """Every value on a chart must also be readable without colour or hover."""
    assert 'class="table-view"' in INDEX_HTML
    assert "Table view" in INDEX_HTML


def test_the_window_control_offers_the_full_history() -> None:
    """Zero is the sentinel the API reads as "no epoch filter"."""
    assert '<option value="0">Full history</option>' in INDEX_HTML


def test_the_rank_that_let_an_object_through_is_shown() -> None:
    """The rank band is the reason an object is on the chart, so it is on the
    chart too, not just in the API response."""
    assert "series.hrr_rank" in INDEX_HTML
    assert "legend-rank" in INDEX_HTML


def test_the_axis_format_follows_the_span() -> None:
    """A full history runs to years, and "29 Jul" on a four-year axis names
    four different days."""
    assert "SPAN_NEEDING_YEAR" in INDEX_HTML
    assert 'year:"numeric"' in INDEX_HTML


def test_the_panel_names_missing_deployment_configuration_on_load() -> None:
    """One gate now stands between an analyst and a chart: the UDL
    credentials. /readyz reports that, so the panel says what is missing
    rather than waiting for the analyst to pick a family and get an error."""
    assert "missingConfiguration" in INDEX_HTML
    assert "udl_configured" in INDEX_HTML
    assert "UDL_USERNAME and UDL_PASSWORD" in INDEX_HTML


def test_no_token_machinery_survives_in_the_interface() -> None:
    """Removed in 0.9.0, at Ash's instruction, and it must stay removed.

    The shared token cost more operator time to diagnose than it protected,
    and it gated the very UDL lookups the charts need. Any reappearance of a
    token box, a bearer header or a sessionStorage token here is a regression,
    not a feature.
    """
    for fragment in [
        "teamToken",
        "team_token",
        "Authorization",
        "token-check",
        "tokenInput",
        "authHeaders",
    ]:
        assert fragment not in INDEX_HTML, f"token machinery is back: {fragment}"


def test_selecting_a_row_plots_that_object() -> None:
    """Ash's requirement, 10 September 2026: choosing one satellite in the
    table plots its history, not just its edit form."""
    assert "showObjectChart" in INDEX_HTML
    assert "/api/udl/object-elements" in INDEX_HTML
    assert "void showObjectChart(record);" in INDEX_HTML


def test_selecting_a_family_plots_it_with_no_further_click() -> None:
    """And choosing a family plots the class immediately."""
    assert 'getElementById("cFamily").addEventListener("change", showFamilyChart)' in (
        INDEX_HTML
    )


def test_there_is_a_way_back_from_one_object_to_the_family() -> None:
    """A view you can enter and not leave is a trap."""
    assert 'id="cWholeFamily"' in INDEX_HTML
    assert (
        'getElementById("cWholeFamily").addEventListener("click", showFamilyChart)'
        in (INDEX_HTML)
    )


def test_the_panel_says_which_scope_it_is_showing() -> None:
    """Two scopes on one panel is a lie waiting to happen unless the heading
    changes with them."""
    assert 'id="chartTitle"' in INDEX_HTML
    assert "Object history" in INDEX_HTML
    assert "Family movement" in INDEX_HTML


def test_one_loader_serves_both_scopes() -> None:
    """The rank gate, the metric rule and the colour rule live on the server.
    Two client-side loaders would be two chances to drift from them."""
    assert INDEX_HTML.count("async function loadCharts(") == 1
    assert "function chartRequest(" in INDEX_HTML


def test_the_hidden_attribute_actually_hides() -> None:
    """`hidden` is only a user-agent `display:none`, and `.btn` sets `display`,
    which beats it. Without this rule the "Whole family" button sat on screen
    in family view. Caught in a browser, not by reading the markup."""
    assert "[hidden]{ display:none !important; }" in INDEX_HTML


def test_the_empty_state_follows_the_scope_on_screen() -> None:
    """A single-object view saying "nothing in this family cleared the checks"
    describes the wrong thing and sends the reader to the wrong place. Caught
    in a browser by selecting a rank 4 object."""
    assert "emptyChartReason" in INDEX_HTML
    assert "This object is not charted. The reason is below." in INDEX_HTML
    assert "Nothing in this family cleared the checks." in INDEX_HTML


def test_relative_mode_anchors_on_the_latest_state() -> None:
    """Ash's rule, 10 September 2026: the reference point for an object is its
    most recent element set, not the first one pulled in.

    Anchoring on the first point in the window made the baseline move whenever
    the window changed, so the same object at the same moment read differently
    at 30 days and at 90. The latest state does not move.
    """
    assert "values[values.length - 1]" in INDEX_HTML
    assert "cumulative[cumulative.length - 1]" in INDEX_HTML
    assert "Relative to latest state" in INDEX_HTML
    assert "most recent element set" in INDEX_HTML


def test_relative_mode_never_differences_against_the_first_point() -> None:
    """The old anchor, so a revert shows up as a failing test rather than a
    quietly different chart."""
    assert "value - values[0]" not in INDEX_HTML
    assert "Relative to window start" not in INDEX_HTML
    assert "first element set in this window" not in INDEX_HTML


def test_the_classification_marking_is_fetched_not_hard_coded() -> None:
    """The one string in this interface that must never be assumed. If the
    fetch fails the banner stays empty, because an invented marking is worse
    than no marking."""
    assert "loadClassification" in INDEX_HTML
    assert "classification_banner" in INDEX_HTML
    assert "UNCLASSIFIED" not in INDEX_HTML


def test_a_provenance_chip_never_relies_on_colour_alone() -> None:
    """Four redundant encodings carry the same meaning: colour, an icon, a
    text label and a border style. Colour alone fails a colour-blind reader
    and a screen reader both."""
    assert "markerChip" in INDEX_HTML
    for marker in ["#i-fact", "#i-inference", "#i-speculation"]:
        assert marker in INDEX_HTML
    for style in ["border-style:solid", "border-style:dashed", "border-style:dotted"]:
        assert style in INDEX_HTML


def test_a_tbc_claim_is_shown_as_unverified_whatever_its_marker() -> None:
    """ "Not yet sourced" is a statement about the evidence; the marker is a
    statement about the assertion. The evidence wins, so an unsourced claim
    can never render as established."""
    assert "function claimTone" in INDEX_HTML
    assert "claim.source_class === SOURCE_CLASS_TBC" in INDEX_HTML
    assert "chip-unverified" in INDEX_HTML
    # The chip itself must say so, not only the border colour. A browser run
    # found an unsourced claim wearing an INFERENCE chip, with colour alone
    # carrying the distinction that matters most.
    assert "function chipFace" in INDEX_HTML
    assert "function markedAsRow" in INDEX_HTML


def test_the_provenance_words_come_from_the_server() -> None:
    """A hard-coded legend would drift from the validators enforcing the same
    vocabulary, and nothing would fail when it did."""
    assert "/api/provenance/legend" in INDEX_HTML
    assert "loadProvenanceLegend" in INDEX_HTML
    for invented in ["Stated directly by a named", "Reasoned from cited facts"]:
        assert invented not in INDEX_HTML, "the legend text is duplicated in the UI"


def test_claim_text_is_escaped_before_it_reaches_the_markup() -> None:
    """Claim statements, citations and owners are analyst-entered text."""
    for expression in [
        "esc(claim.statement)",
        "esc(claim.asserted_by)",
        "esc(citation)",
        "esc(claim.owner)",
    ]:
        assert expression in INDEX_HTML


def test_only_an_http_source_url_becomes_a_link() -> None:
    """A citation is analyst-entered, so a javascript: URL in an href would
    execute on click."""
    assert "function safeUrl" in INDEX_HTML
    assert 'raw.startsWith("https://")' in INDEX_HTML
    assert 'rel="noopener noreferrer"' in INDEX_HTML


def test_the_provenance_empty_states_say_why_and_what_next() -> None:
    """An empty panel that says nothing reads as a fault. Both states name the
    reason and the remedy, and neither implies something is being withheld."""
    assert "Choose a row in the catalogue" in INDEX_HTML
    assert "has no recorded claims yet" in INDEX_HTML
    assert "Nothing is being " in INDEX_HTML


def test_the_empty_chart_state_does_not_invent_a_cause() -> None:
    """It used to say every member lacked a NORAD ID, which since the rank
    gate is usually false: the real reasons are in the skipped list."""
    assert "No member of this family has a NORAD ID" not in INDEX_HTML
    assert "Nothing in this family cleared the checks" in INDEX_HTML


def test_the_browser_tab_says_legion() -> None:
    assert "<title>Legion · Tracked Systems</title>" in INDEX_HTML


def test_the_favicon_needs_no_network_request() -> None:
    """A data URI keeps the icon in the one file the app serves, works
    offline, and stops the browser asking for /favicon.ico and getting a 404.

    Plain SVG rather than base64 on purpose: a long base64 blob is the shape a
    secret-detection scanner flags on entropy, and this app has to pass one.
    """
    assert 'rel="icon"' in INDEX_HTML
    assert "data:image/svg+xml,%3Csvg" in INDEX_HTML
    assert "base64" not in INDEX_HTML


def test_every_icon_reference_resolves_to_a_defined_symbol() -> None:
    """A typo in a sprite id fails silently: nothing renders, no error.

    References are counted wherever they appear, not only in a literal
    `<use href="#...">`. The provenance chips pick their icon from a lookup
    keyed by marker, so the id lives in a JavaScript string. Counting only the
    static form reported three genuinely-used symbols as unused, and would
    equally have missed a typo in a dynamic one.
    """
    defined = set(re.findall(r'<symbol id="(i-[\w-]+)"', INDEX_HTML))
    # A declaration is `id="i-fact"` with no hash, so every `#i-...` in the
    # file is a reference, whether it sits in markup or in a JavaScript string.
    used = set(re.findall(r"#(i-[\w-]+)", INDEX_HTML))
    assert used, "The UI should be using the sprite"
    assert used <= defined, f"No symbol defined for: {used - defined}"
    assert defined == used, f"Sprite carries unused symbols: {defined - used}"


def test_icons_are_decorative_and_never_the_only_label() -> None:
    """Each sits beside text that says the same thing, so a screen reader
    should skip it rather than announce it twice."""
    icons = re.findall(r"<svg class=\"(?:icon|mark)\"[^>]*>", INDEX_HTML)
    assert icons
    assert all('aria-hidden="true"' in icon for icon in icons)


def test_the_submit_button_label_is_its_own_element() -> None:
    """The button holds an icon as well as a label. Rewriting the button's
    textContent, which is what the code used to do, would delete the icon."""
    assert 'id="submitLabel"' in INDEX_HTML
    assert 'getElementById("submitBtn").textContent' not in INDEX_HTML


def test_status_reads_as_shape_as_well_as_colour() -> None:
    """A status must not depend on colour alone."""
    assert '<use href="#i-status"/>' in INDEX_HTML
    assert ".pill.onorbit .icon{ fill:currentColor; }" in INDEX_HTML


def test_the_catalogue_pages_rather_than_scrolling() -> None:
    """Forty-nine rows in one scroll was the complaint."""
    assert 'id="fRows"' in INDEX_HTML
    assert "DEFAULT_ROWS = 15" in INDEX_HTML
    assert 'data-page="next"' in INDEX_HTML
    assert 'data-page="prev"' in INDEX_HTML
    assert 'aria-label="Previous page"' in INDEX_HTML


def test_the_stored_row_choice_is_validated_as_a_string() -> None:
    """The bug this pins: Number(null) and Number("") are both 0, which is the
    "All" sentinel, so parsing before validating made an absent preference
    mean "show everything" - the opposite of the default, on every first
    visit. Validate the raw string against the option list instead."""
    assert "ROW_OPTIONS.has(raw)" in INDEX_HTML
    assert "Number(localStorage.getItem" not in INDEX_HTML


def test_the_page_number_is_clamped_before_slicing() -> None:
    """A filter can shrink the list under the page you are on, and a page past
    the end renders an empty table with no clue why."""
    assert "currentPage = Math.min(Math.max(1, currentPage), pageCount(" in INDEX_HTML


def test_reordering_or_refiltering_returns_to_the_first_page() -> None:
    """Page 3 of a different ordering is a different set of rows."""
    assert "reloadFromFirstPage" in INDEX_HTML
    assert INDEX_HTML.count("currentPage = 1;") >= 3


def test_row_storage_is_wrapped_against_a_throwing_accessor() -> None:
    """A private window or blocked site data throws on access rather than
    returning null, and the table must still render."""
    stored = INDEX_HTML[INDEX_HTML.index("function storedRows()") :]
    assert "try{" in stored[:200] and "catch" in stored[:400]


# --- candidate systems, verified in a browser first -------------------------


def test_a_candidate_is_marked_by_text_and_not_only_by_colour() -> None:
    """The badge has to survive a colour-blind reader and a screen reader.

    Same rule the provenance chips follow. A dotted border and a muted colour
    are the supporting encodings, never the whole signal.
    """
    assert 'const CANDIDATE_WORD = "Candidate";' in INDEX_HTML
    assert "esc(CANDIDATE_WORD)" in INDEX_HTML


def test_a_candidate_shows_where_it_came_from_and_who_closes_it() -> None:
    """A candidate that names no owner is the entry that sits unresolved for a
    year. The panel reads both fields off the record rather than describing
    them in prose that could drift."""
    assert "record.source_citation" in INDEX_HTML
    assert "record.verify_owner" in INDEX_HTML


def test_an_unknown_launch_year_reads_as_a_dash() -> None:
    """A candidate has no launch year, and `esc(null)` renders the four
    characters "null" in the table. Caught in a browser, not by a test."""
    assert "esc(s.launch_year || EM_DASH)" in INDEX_HTML
    assert "esc(s.launch_year)}" not in INDEX_HTML
