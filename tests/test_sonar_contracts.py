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

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
# sonar-project.properties sets sonar.tests=tests, so the platform counts
# duplicated literals in the test tree too. Scanning only src let a new issue
# through in 0.4.7 and failed the gate.
SCANNED_TREES = (SRC, ROOT / "tests")
INDEX_HTML = SRC / "static" / "index.html"

# S1192 fires on a literal repeated three or more times. Empirically the
# platform only counts literals containing whitespace: identifier-shaped
# values (field names, ids, enum values like "onorbit") are exempt, which is
# why "coplanar" x49 was never reported while "4 years" x3 was.
MIN_OCCURRENCES = 3


def _python_files() -> list[pathlib.Path]:
    return [path for tree in SCANNED_TREES for path in sorted(tree.rglob("*.py"))]


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
        f"{path.relative_to(ROOT)}:{min(lines)}": (text[:60], len(lines))
        for tree in SCANNED_TREES
        for path in sorted(tree.rglob("*.py"))
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


def _logger_error_calls(node: ast.AST) -> list[ast.Call]:
    """`logger.error(...)` calls anywhere under this node."""
    return [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "error"
        and isinstance(call.func.value, ast.Name)
        and "log" in call.func.value.id
    ]


def test_error_logging_inside_a_handler_uses_exception() -> None:
    """SonarQube: "Use logging.exception() instead."

    This rule cost three upload cycles. It fired on one line added in 0.4.7,
    and because the gate's only visible message is "Quality Gate FAILED", three
    rounds of fixing other conditions changed nothing. Inside an except block,
    `logger.error` discards the traceback that makes the record worth having.
    """
    offenders = [
        f"{path.relative_to(ROOT)}:{call.lineno}"
        for path in _python_files()
        for handler in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(handler, ast.ExceptHandler)
        for call in _logger_error_calls(handler)
    ]
    assert offenders == [], (
        f"Use logger.exception() inside an except block, not logger.error(): {offenders}"
    )


# --- The JavaScript rules the gate raised against src/static/index.html -----
#
# These are heuristics on the source text, not a parse: there is no JavaScript
# parser in this project's dependencies and adding one to satisfy a lint mirror
# would be a poor trade against the Dependency Scanning gate. They were
# calibrated against the 0.6.0 upload, where the platform reported nested
# ternaries at lines 376, 377, 396, 591 (twice), 679 and 902, a nested template
# literal at 835 and a getAttribute at 409. The detectors below found every one
# of those, plus one further getAttribute at 405 that the platform did not
# raise because it was not new code. Over-reporting is the safe direction.

NESTED_TERNARY_PATTERNS = (
    # A second ? inside the condition-to-colon span: a ? (b ? c : d) : e
    r"\?[^?:;{}]*\?",
    # A second ? in the else branch: a ? b : c ? d : e
    r"\?[^?:;]*:[^?:;{}]*\?",
)


def _statements(text: str) -> list[tuple[int, str]]:
    """Fold continuation lines back onto their statement.

    A ternary is often written across three lines, with the ? and the : each
    opening a line. Reading line by line would miss it.
    """
    folded: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if folded and stripped.startswith(("?", ":")):
            first, joined = folded[-1]
            folded[-1] = (first, f"{joined} {stripped}")
        else:
            folded.append((number, stripped))
    return folded


def test_no_nested_ternary_operations() -> None:
    """SonarQube typescript:S3358."""
    offenders = []
    for number, statement in _statements(INDEX_HTML.read_text(encoding="utf-8")):
        if statement.startswith(("//", "*")):
            continue
        # ?? and ?. are not ternaries.
        plain = statement.replace("??", "").replace("?.", "")
        if any(re.search(pattern, plain) for pattern in NESTED_TERNARY_PATTERNS):
            offenders.append(number)
    assert offenders == [], (
        f"Extract these nested ternaries into named helpers: lines {offenders}"
    )


def _nests_a_template(line: str) -> bool:
    """True when a backtick opens inside another template literal's slot."""
    depth = 0
    inside = False
    position = 0
    while position < len(line):
        character = line[position]
        if character == "`":
            if inside and depth > 0:
                return True
            inside = not inside
        elif inside and line.startswith("${", position):
            depth += 1
            position += 1
        elif inside and character == "}" and depth > 0:
            depth -= 1
        position += 1
    return False


def test_no_nested_template_literals() -> None:
    """SonarQube typescript:S4624 - a backtick inside another template's slot."""
    offenders = [
        number
        for number, line in enumerate(
            INDEX_HTML.read_text(encoding="utf-8").splitlines(), 1
        )
        if _nests_a_template(line)
    ]
    assert offenders == [], (
        f"Build the inner string in its own statement: lines {offenders}"
    )


def test_data_attributes_are_read_through_dataset() -> None:
    """SonarQube typescript:S6754 - prefer .dataset over getAttribute."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'getAttribute("data-' not in html
    assert "getAttribute('data-" not in html


def test_the_start_up_fetches_are_awaited() -> None:
    """SonarQube: prefer top-level await over calling an async function.

    A module script is deferred, so the DOM is already parsed by the time it
    runs, and awaiting means a failed first load surfaces rather than becoming
    an unhandled rejection.
    """
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert '<script type="module">' in html
    assert "await loadSystems();" in html
    assert "await loadFamilies();" in html


# --- The CSS rules the gate raised, calibrated against the 0.7.0 upload -----
#
# The platform reported four duplicate selectors there: .pill, .btn,
# .panel h2 and .token-bar button, each declared once in the original
# stylesheet and again in the icon block added in 0.6.4. The detector below
# finds exactly those four in that file and none in this one.


def _stylesheet(html: str) -> str:
    return html[html.index("<style>") : html.index("</style>")]


def duplicate_selectors(html: str) -> dict[str, int]:
    """Top-level selectors declared in more than one block.

    Only top-level rules: a nested rule inside @media is a different context
    and the platform does not raise it. Selectors are compared verbatim, since
    that is what the rule reports.
    """
    seen: collections.Counter[str] = collections.Counter()
    for match in re.finditer(r"(?m)^([^\s@/][^{}]*)\{", _stylesheet(html)):
        seen[match.group(1).strip()] += 1
    return {selector: count for selector, count in seen.items() if count > 1}


def test_no_selector_is_declared_twice() -> None:
    """SonarQube css:S4667 - a second block for the same selector.

    Splitting one element's styling across two places is how the two drift,
    and the rule fires whichever order they sit in.
    """
    offenders = duplicate_selectors(INDEX_HTML.read_text(encoding="utf-8"))
    assert offenders == {}, (
        f"Fold these into the block that already owns the selector: {offenders}"
    )


def test_a_membership_test_uses_a_set() -> None:
    """SonarQube: a constant list used only for existence checks wants a Set.

    A Set says what the collection is for, and says it in the type rather than
    in a comment.
    """
    html = INDEX_HTML.read_text(encoding="utf-8")
    offenders = [
        name
        for name in re.findall(r"const (\w+) = \[", html)
        if f"{name}.includes(" in html
    ]
    assert offenders == [], (
        f"Declare these as `new Set([...])` and use .has(): {offenders}"
    )
