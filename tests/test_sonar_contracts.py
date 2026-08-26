"""Local mirrors of the SonarQube rules that failed the platform's quality
gate, so a regression is caught by `pytest` rather than by a failed upload.

The gate is "new issues: 0", which means a single reintroduced duplicate
literal fails the whole submission. These checks were calibrated against the
platform's own report: the S1192 mirror reproduced all 26 findings in
`seed_data.py` exactly, same literals, same first-occurrence lines, same
counts, with nothing missing and nothing extra.
"""

from __future__ import annotations

import ast
import collections
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"
INDEX_HTML = SRC / "static" / "index.html"

# S1192 fires on a literal repeated three or more times. Empirically the
# platform only counts literals containing whitespace: identifier-shaped
# values (field names, ids, enum values like "onorbit") are exempt, which is
# why "coplanar" x49 was never reported while "4 years" x3 was.
MIN_OCCURRENCES = 3


def _duplicated_literals(path: pathlib.Path) -> dict[str, list[int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    seen: dict[str, list[int]] = collections.defaultdict(list)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            seen[node.value].append(node.lineno)
    return {
        text: lines
        for text, lines in seen.items()
        if len(lines) >= MIN_OCCURRENCES and re.search(r"\s", text)
    }


def test_no_duplicated_string_literals() -> None:
    """SonarQube python:S1192."""
    offenders = {
        f"{path.relative_to(SRC.parent)}:{min(lines)}": (text[:60], len(lines))
        for path in sorted(SRC.rglob("*.py"))
        for text, lines in _duplicated_literals(path).items()
    }
    assert offenders == {}, (
        f"Define a constant for these repeated literals: {offenders}"
    )


def test_status_role_is_expressed_as_output_element() -> None:
    """SonarQube Web:S6819 - <output> carries the status role natively."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'role="status"' not in html, (
        "Use <output> rather than an explicit status role"
    )
    assert "<output" in html, "The live-region elements should still be present"


def test_dev_entrypoint_does_not_hardcode_all_interfaces() -> None:
    """The container binds every interface via the Dockerfile's gunicorn CMD.

    The local-dev entrypoint must not, or Sonar raises it as a vulnerability
    and a laptop dev server is exposed to the local network for no benefit.
    """
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        literals = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        assert "0.0.0.0" not in literals, f"{path} hardcodes an all-interfaces bind"
