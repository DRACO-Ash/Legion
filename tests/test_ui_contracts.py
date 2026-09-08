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


def test_a_rejected_token_and_a_missing_one_read_differently() -> None:
    """ "Set the team token" is useless advice to someone who just did.

    A 401 has two causes: nothing in this tab, or a value that does not match
    the deployment. The UI has to tell them apart, and it does it by comparing
    the length it is sending against the length /readyz reports.
    """
    assert "NO_TOKEN_HERE" in INDEX_HTML
    assert "TOKEN_REJECTED" in INDEX_HTML
    assert "team_token_len" in INDEX_HTML
    assert "tokenRejectedMessage" in INDEX_HTML
    # The old single message mapped both causes onto the wrong advice.
    assert "401:" not in INDEX_HTML


def test_the_token_box_says_how_long_the_token_it_holds_is() -> None:
    """The one number that identifies a mismatch without exposing a secret."""
    assert "held.length" in INDEX_HTML


def test_the_token_box_warns_that_it_is_per_tab() -> None:
    """sessionStorage does not carry across tabs, and the App Store opens the
    app in a new one."""
    assert "per browser tab" in INDEX_HTML


def test_the_panel_names_missing_deployment_configuration_on_load() -> None:
    """Three gates stand between an analyst and a chart: the team token, the
    UDL credentials, and the rank band. Two of them are deployment
    configuration, and /readyz reports both, so the panel says what is missing
    rather than waiting for the analyst to pick a family and get a 503."""
    assert "missingConfiguration" in INDEX_HTML
    assert "udl_configured" in INDEX_HTML
    assert "UDL_USERNAME and UDL_PASSWORD" in INDEX_HTML


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
    """A typo in a sprite id fails silently: nothing renders, no error."""
    defined = set(re.findall(r'<symbol id="(i-[\w-]+)"', INDEX_HTML))
    used = set(re.findall(r'<use href="#(i-[\w-]+)"', INDEX_HTML))
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
