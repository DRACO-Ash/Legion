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
