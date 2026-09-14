"""Every SonarQube rule the platform has actually fired, as a local check.

Separate from `test_sonar_contracts.py` only because that file was getting
long. The discipline is the same and is the whole point of this module: a
rule goes in here the moment the platform reports it, calibrated against the
upload that reported it, and it never comes out.

`docs/SONAR-RULE-REGISTER.md` is the index. Every rule below names the upload
that found it, because a mirror written from a guess about what Sonar might
dislike is worth very little, and one written from a real finding is worth a
whole upload cycle.

**The 0.15.0 upload reported eighteen new issues and this file exists because
every local check passed.** Eight distinct rules, all in code written in
Phases 5 and 6. The lesson is not that the mirrors were wrong; it is that a
mirror only covers the rules somebody has already been caught by, so the set
has to grow every time the platform finds something new.
"""

from __future__ import annotations

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
INDEX_HTML = (SRC / "static" / "index.html").read_text(encoding="utf-8")

# Elements that carry no interactive semantics of their own. Giving one an
# interactive role, or a tabindex, is the accessibility smell the platform
# reported twice on the command palette.
NON_INTERACTIVE = ("div", "span", "p", "ul", "ol", "li", "pre", "section", "table")
INTERACTIVE_ROLES = (
    "listbox",
    "option",
    "button",
    "menu",
    "menuitem",
    "tab",
    "combobox",
)


def _python_files() -> list[pathlib.Path]:
    return sorted(SRC.rglob("*.py"))


# --- FastAPI, reported against 0.15.0 ---------------------------------------


ROUTE_METHODS = {"get", "post", "patch", "put", "delete"}


def _route_decorators(tree: ast.AST) -> list[ast.Call]:
    """Every decorator-style route registration.

    `add_api_route` is deliberately not included: the rule that fired is
    written against the decorator form, and a registration call carries its
    path as an ordinary argument that Sonar has no reason to parse as a
    route template. `test_every_route_path_is_a_literal` covers both forms
    for the invariant that actually matters.
    """
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ROUTE_METHODS
        and isinstance(node.func.value, ast.Name)
        and "router" in node.func.value.id
    ]


def _registrations(tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_api_route"
    ]


def test_a_route_path_is_a_literal_string() -> None:
    """SonarQube: "Add path parameter X to the function signature."

    Reported ten times against 0.15.0, all on `object_lists.py`, naming
    `{system_id`, `{entry_id` and `path` as missing parameters that are in
    fact present. Sonar cannot evaluate an f-string, so it reads the template
    source and treats every brace token in it as a path parameter the
    function does not declare.

    The finding is a false positive about the signature and a true one about
    the code: a route whose path is computed cannot be checked by any tool,
    including a human reading the file. Pass the literal in.
    """
    offenders = [
        f"{path.relative_to(ROOT)}:{call.lineno}"
        for path in _python_files()
        for call in _route_decorators(ast.parse(path.read_text(encoding="utf-8")))
        if call.args and not isinstance(call.args[0], ast.Constant)
    ]
    assert offenders == [], (
        f"A route decorator's path must be a literal string: {offenders}"
    )


PATH_KEYWORDS = {"collection_path", "entry_path"}


def _list_registrations(tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "register_object_list"
    ]


def _has_computed_path(call: ast.Call) -> bool:
    return any(
        keyword.arg in PATH_KEYWORDS and not isinstance(keyword.value, ast.Constant)
        for keyword in call.keywords
    )


def test_every_route_path_is_written_out_by_its_caller() -> None:
    """The invariant behind the rule, checked where the path is authored.

    Inside the factory the path can only ever be a variable; the literal
    lives at the call site, which is where a person greps for a route. So
    this checks the callers: every `collection_path` and `entry_path` handed
    to `register_object_list` is a literal string, and any that is not would
    make the route unfindable by tool or by eye.
    """
    offenders = [
        f"{path.relative_to(ROOT)}:{call.lineno}"
        for path in _python_files()
        for call in _list_registrations(ast.parse(path.read_text(encoding="utf-8")))
        if _has_computed_path(call)
    ]
    assert offenders == [], f"Route paths must be written out: {offenders}"


def test_fastapi_parameters_use_annotated() -> None:
    """SonarQube: "Use Annotated type hints for FastAPI dependency injection."

    Reported once against 0.15.0, on `operability.py`. `x: T = Query(...)`
    puts a function call in a default argument, which is also what ruff's
    B008 objects to, and the Annotated form says the same thing without one.
    """
    markers = {"Query", "Depends", "Path", "Header", "Cookie", "Body", "Form"}
    offenders = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            for default in node.args.defaults:
                if (
                    isinstance(default, ast.Call)
                    and isinstance(default.func, ast.Name)
                    and default.func.id in markers
                ):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == [], (
        f"Use Annotated[T, Query(...)] rather than a call in a default: {offenders}"
    )


# --- accessibility, reported against 0.15.0 ---------------------------------


def _tags(html: str, name: str) -> list[tuple[int, str]]:
    """Every opening tag of one element, with its 1-based line number."""
    found = []
    for match in re.finditer(rf"<{name}\b[^>]*>", html, re.IGNORECASE | re.DOTALL):
        found.append((html[: match.start()].count("\n") + 1, match.group(0)))
    return found


def test_every_input_carries_a_label() -> None:
    """SonarQube: "Associate a valid label to this input field."

    Reported against 0.15.0 on the command palette's search box, which had a
    placeholder and nothing else. A placeholder is not a label: it vanishes
    the moment anything is typed, and a screen reader may never announce it.
    """
    labelled_ids = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', INDEX_HTML))
    # An input wrapped in a label is labelled too. Without this the mirror
    # flags `<label><input ...> Include archived</label>`, which the platform
    # correctly does not report, and a mirror that over-fires is noise.
    wrapped = set(re.findall(r"<label\b[^>]*>.*?</label>", INDEX_HTML, re.DOTALL))
    offenders = []
    for line, tag in _tags(INDEX_HTML, "input"):
        if 'type="hidden"' in tag:
            continue
        element_id = re.search(r'\bid="([^"]+)"', tag)
        has_own_label = "aria-label=" in tag or "aria-labelledby=" in tag
        inside_label = any(tag in block for block in wrapped)
        if (
            not has_own_label
            and not inside_label
            and (element_id is None or element_id.group(1) not in labelled_ids)
        ):
            offenders.append(line)
    assert offenders == [], (
        f"Give these inputs a <label for> or an aria-label: lines {offenders}"
    )


def test_no_element_fakes_a_dialog_with_a_role() -> None:
    """SonarQube: "Use <dialog> instead of the dialog role."

    Reported against 0.15.0 on the palette overlay. The real element brings
    focus trapping, Escape handling and inertness for free; the role brings
    the promise of them and none of the behaviour.
    """
    offenders = [
        line for line, tag in _tags(INDEX_HTML, "[a-z]+") if 'role="dialog"' in tag
    ]
    assert offenders == [], f"Use a real <dialog> element: lines {offenders}"


def test_no_non_interactive_element_wears_an_interactive_role() -> None:
    """SonarQube: "Non-interactive elements should not be assigned interactive
    roles", and "Use <datalist> or <select> instead of the listbox role".

    Both reported against 0.15.0 on the palette's results list. A `<ul>` with
    `role="listbox"` promises keyboard semantics the element does not have,
    and assistive technology then announces a control that does not behave
    like one.
    """
    offenders = []
    for element in NON_INTERACTIVE:
        for line, tag in _tags(INDEX_HTML, element):
            role = re.search(r'\brole="([^"]+)"', tag)
            if role and role.group(1) in INTERACTIVE_ROLES:
                offenders.append(f"line {line}: <{element} role={role.group(1)}>")
    assert offenders == [], (
        f"Use a real interactive element rather than a role: {offenders}"
    )


def test_tabindex_only_on_interactive_elements() -> None:
    """SonarQube: "tabIndex should only be declared on interactive elements."

    Reported against 0.15.0 on the briefing `<pre>`. Putting the briefing in
    the tab order does not make it operable, it just adds a stop that does
    nothing. A `<tr>` carrying `role="button"` is interactive and is exempt.
    """
    offenders = []
    for element in NON_INTERACTIVE:
        for line, tag in _tags(INDEX_HTML, element):
            if "tabindex=" in tag.lower() and "role=" not in tag.lower():
                offenders.append(f"line {line}: <{element} tabindex>")
    assert offenders == [], (
        f"Remove tabindex, or use an element that is genuinely interactive: {offenders}"
    )


# --- JavaScript, reported against 0.15.0 ------------------------------------


def _script_body(html: str) -> str:
    start = html.index('<script type="module">')
    return html[start : html.index("</script>", start)]


def _nests_a_template(text: str) -> bool:
    """True when a backtick opens inside another template literal's slot.

    Scans the whole script rather than a line at a time. **The previous
    version scanned line by line and missed a nesting that spanned three**,
    which is how 0.15.0 shipped one: the outer template and its `${` opened
    on one line, the inner backtick was on the next, and no single line ever
    held both.
    """
    depth = 0
    inside = False
    position = 0
    while position < len(text):
        character = text[position]
        if character == "`":
            if inside and depth > 0:
                return True
            inside = not inside
        elif inside and text.startswith("${", position):
            depth += 1
            position += 1
        elif inside and character == "}" and depth > 0:
            depth -= 1
        position += 1
    return False


def test_no_nested_template_literal_anywhere_in_the_script() -> None:
    """SonarQube: "Refactor this code to not use nested template literals."

    Reported against 0.15.0 on the comparison table's capabilities cell,
    where a template opened inside a ternary inside another template's slot,
    across three lines.
    """
    assert not _nests_a_template(_script_body(INDEX_HTML)), (
        "A template literal opens inside another one's ${...} slot. Build the "
        "inner string in a named variable first."
    )


def test_find_is_not_used_as_a_boolean_test() -> None:
    """SonarQube: "Prefer `.some(…)` over `.find(…)`."

    Reported against 0.15.0 where a `.find()` result was immediately
    defaulted and compared. `.some()` says what is meant, stops at the first
    match, and cannot be mistaken for code that wants the found item.
    """
    body = _script_body(INDEX_HTML)
    offenders = [
        match.group(0)[:70]
        for match in re.finditer(
            r"\(\s*[\w.]+\.find\([^;]{0,120}?\|\|\s*\{\}\s*\)", body
        )
    ]
    assert offenders == [], f"Use .some(...) to test, not .find(...): {offenders}"


def test_the_dialog_overlay_is_scoped_to_its_open_state() -> None:
    """Moving the palette to a real `<dialog>` introduced a regression a test
    could not have predicted, and a browser found in one run.

    A bare `.palette{display:flex}` beats the user-agent rule that hides a
    closed dialog, so `close()` left it on screen and every subsequent key
    went to it: the slash guard, Escape and the catalogue keyboard all
    appeared broken. The display rule is scoped to `[open]`.
    """
    # Parsed as rule blocks, not lines. The declaration sits on a
    # continuation line, and a line-based check missed it: the same blind
    # spot as the nested-template mirror, made twice in one session.
    styles = INDEX_HTML.split("<style>")[1].split("</style>")[0]
    blocks = re.findall(r"([^{}]+)\{([^{}]*)\}", styles)
    palette_rules = [
        selector.strip()
        for selector, body in blocks
        if selector.strip().startswith(".palette") and "display:flex" in body
    ]
    assert palette_rules, "The palette overlay rule has moved; re-check this."
    assert all("[open]" in rule for rule in palette_rules), palette_rules
