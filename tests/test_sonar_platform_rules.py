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


TEST_SHAPES = (
    r"if\s*\(\s*!?\s*{name}\s*\)",  # if(x) / if(!x)
    r"!\s*{name}\b",  # !x anywhere
    r"\b{name}\s*\?",  # x ? a : b
    r"(?:&&|\|\|)\s*{name}\b",  # && x
    r"\b{name}\s*(?:&&|\|\|)",  # x &&
)


def _uses_of(name: str, line: str) -> list[str]:
    """Classify each mention of `name` as a truthiness test or a real read.

    A read is anything that wants the found object: a dereference, an index,
    a return, or being passed to something. The distinction is the whole of
    the rule, and getting it wrong in the lenient direction is what let line
    2001 through, while getting it wrong in the strict direction would flag
    line 703, where the found column really is used.
    """
    found = []
    for match in re.finditer(rf"\b{name}\b", line):
        window = line[max(0, match.start() - 12) : match.end() + 6]
        if any(re.search(shape.format(name=name), window) for shape in TEST_SHAPES):
            found.append("test")
        else:
            found.append("read")
    return found


FIND_BINDING = re.compile(r"^\s*(?:const|let|var)\s+(\w+)\s*=\s*[\w.]+\.find\(")


def _find_results_used_only_as_a_test(body: str) -> list[str]:
    """Every `.find()` whose result is never actually read.

    The scan stops at the end of the enclosing function, which in this file
    is an unindented closing brace. Nothing here needs a JavaScript parser:
    the question is only whether the bound name is ever dereferenced.
    """
    lines = body.splitlines()
    offenders = []
    for index, line in enumerate(lines):
        binding = FIND_BINDING.match(line)
        if not binding:
            continue
        name = binding.group(1)
        uses = []
        for follower in lines[index + 1 :]:
            if follower.startswith("}"):
                break
            uses.extend(_uses_of(name, follower))
        if uses and all(kind == "test" for kind in uses):
            offenders.append(f"index.html script line {index + 1}: {name}")
    return offenders


def test_find_is_not_used_as_a_boolean_test() -> None:
    """SonarQube: "Prefer `.some(…)` over `.find(…)`."

    Reported against 0.15.0 where a `.find()` result was immediately
    defaulted and compared. `.some()` says what is meant, stops at the first
    match, and cannot be mistaken for code that wants the found item.

    **Reported again at line 2001 on 0.15.2, and this mirror missed it**,
    because the first version was written from the one instance in front of
    it: a `.find()` wrapped in `(… || {})`. The rule is about the result
    being used only as a truthiness test, and the second instance assigned it
    to a name first and then wrote `if(record)`. The same mistake as the
    line-based scanners: a mirror written from an example covers the example.

    This version asks the question the rule asks. It takes every
    `const NAME = ….find(…)` and looks at how NAME is used for the rest of
    its function. If it is never dereferenced, never indexed and never
    returned, then nothing wants the found item and `.some()` is what was
    meant. Calibrated against the two legitimate uses in this same file,
    at lines 703 and 800, where the value really is read.
    """
    offenders = _find_results_used_only_as_a_test(_script_body(INDEX_HTML))
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


# --- scripts/ is analysed too, reported against 0.15.2 -----------------------
#
# The headline finding of the 0.15.2 upload, and the reason nine of its
# fourteen issues were invisible here. `sonar-project.properties` sets
# `sonar.sources=src`, and every mirror in this repository read that and
# scanned `src` and `tests`. The platform reported issues in
# `scripts/check-quality-gate.sh` and `scripts/udl_live_check.py` anyway.
#
# That is a FACT from a job report, not a theory about the scanner: whatever
# the property says, the analysis reaches `scripts/`. Every mirror that walks
# a tree must therefore walk this one as well.


SCRIPTS = ROOT / "scripts"


FUNCTION_OPENS = re.compile(r"^\s*(function\s+)?[\w:-]+\s*\(\)\s*\{")


def _is_a_plain_copy(node: ast.DictComp) -> bool:
    """True when the comprehension rebuilds its source unchanged."""
    if len(node.generators) != 1:
        return False
    generator = node.generators[0]
    if generator.ifs or not isinstance(generator.target, ast.Tuple):
        return False
    if not (isinstance(node.key, ast.Name) and isinstance(node.value, ast.Name)):
        return False
    names = [e.id for e in generator.target.elts if isinstance(e, ast.Name)]
    return len(names) == 2 and [node.key.id, node.value.id] == names


def _all_python_files() -> list[pathlib.Path]:
    """Every Python file the platform has been observed to analyse."""
    return sorted(
        path
        for tree in (SRC, ROOT / "tests", SCRIPTS)
        for path in tree.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _shell_files() -> list[pathlib.Path]:
    return sorted(SCRIPTS.rglob("*.sh"))


def _shell_bodies() -> list[tuple[pathlib.Path, list[str]]]:
    return [
        (path, path.read_text(encoding="utf-8").splitlines()) for path in _shell_files()
    ]


def test_scripts_are_scanned_by_every_mirror_that_walks_a_tree() -> None:
    """The 0.15.2 lesson, pinned so it cannot quietly regress.

    If someone narrows the file set back to `src` because the properties file
    says `sonar.sources=src`, this fails and says why.
    """
    assert SCRIPTS.is_dir(), "scripts/ must exist for the mirrors to cover it"
    scanned = {path.parts[-2] for path in _all_python_files()}
    assert "scripts" in scanned, (
        "The platform reported issues in scripts/ on 0.15.2 despite "
        "sonar.sources=src. Every mirror must scan it."
    )


# --- Shell, reported against 0.15.2 -----------------------------------------


def test_shell_conditionals_use_double_brackets() -> None:
    """SonarQube: "Use '[[' instead of '[' for conditional tests."

    Six of the fourteen findings on 0.15.2, all in one new shell script. The
    single-bracket form word-splits an unquoted expansion and does not support
    pattern matching, so the rule is a real one rather than a style
    preference.
    """
    offenders = [
        f"{path.relative_to(ROOT)}:{number}"
        for path, lines in _shell_bodies()
        for number, line in enumerate(lines, 1)
        if re.search(r"(^|[;&|]|\b(?:if|while|until|elif))\s*!?\s*\[\s", line)
        and not re.search(r"\[\[", line)
    ]
    assert offenders == [], f"Use [[ ]] for shell conditionals: {offenders}"


def test_shell_functions_return_explicitly() -> None:
    """SonarQube: "Add an explicit return statement at the end of the function."

    Without one a function returns the status of whatever ran last, which
    makes its exit code an accident of its final line rather than a decision.
    """
    offenders = []
    for path, lines in _shell_bodies():
        open_at = None
        for number, line in enumerate(lines, 1):
            if re.match(r"^\s*(function\s+)?[\w:-]+\s*\(\)\s*\{", line):
                open_at = number
            elif open_at is not None and re.match(r"^\}", line):
                body = lines[open_at : number - 1]
                if not any(re.match(r"^\s*return\b", entry) for entry in body):
                    offenders.append(f"{path.relative_to(ROOT)}:{open_at}")
                open_at = None
    assert offenders == [], f"A shell function needs an explicit return: {offenders}"


def _bare_positional(line: str) -> bool:
    """A positional parameter used directly, rather than named first."""
    stripped = line.split("#", 1)[0]
    if not re.search(r"\$\{?[1-9]\}?", stripped):
        return False
    return not re.match(r"^\s*local\s+\w+=", stripped)


def _function_body_lines(lines: list[str]) -> list[tuple[int, str]]:
    """Every line inside a shell function, with its 1-based number."""
    found: list[tuple[int, str]] = []
    inside = False
    for number, line in enumerate(lines, 1):
        if FUNCTION_OPENS.match(line):
            inside = True
        elif inside and line.startswith("}"):
            inside = False
        elif inside:
            found.append((number, line))
    return found


def test_shell_functions_name_their_positional_parameters() -> None:
    """SonarQube: "Assign this positional parameter to a local variable."

    `$1` deep inside a function body says nothing about what it holds. A
    named local does, and it survives a later `shift`.
    """
    offenders = [
        f"{path.relative_to(ROOT)}:{number}"
        for path, lines in _shell_bodies()
        for number, line in _function_body_lines(lines)
        if _bare_positional(line)
    ]
    assert offenders == [], (
        f"Assign a positional parameter to a named local first: {offenders}"
    )


# --- Python in scripts/, reported against 0.15.2 ----------------------------


def test_no_dict_comprehension_merely_copies() -> None:
    """SonarQube: "Replace this comprehension with passing the iterable to the
    dict constructor call."

    `{k: v for k, v in items.items()}` is `dict(items)` written long. The
    comprehension form hides that nothing is being filtered or transformed.
    """
    offenders = [
        f"{path.relative_to(ROOT)}:{node.lineno}"
        for path in _all_python_files()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.DictComp) and _is_a_plain_copy(node)
    ]
    assert offenders == [], (
        f"Use dict(...) rather than a copying comprehension: {offenders}"
    )


def test_a_caller_supplied_path_is_checked_before_it_is_written() -> None:
    """SonarQube, reported as a Vulnerability on 0.15.2: "LLMs running this
    code with faulty CLI arguments can escape file system restrictions."

    `--out` is caller input and went straight to `Path(...).write_text`. The
    same class of hole as the `--base-url` one `checked_url` already closes,
    and it is closed the same way: a named checker, used at the boundary.
    """
    source = (SCRIPTS / "udl_live_check.py").read_text(encoding="utf-8")
    assert "def checked_out_path(" in source, (
        "A caller-supplied output path needs a named validator"
    )
    written = re.findall(r"Path\(([^)]*)\)\.write_text", source)
    unchecked = [call for call in written if "checked_out_path" not in call]
    assert unchecked == [], f"Validate the path before writing to it: {unchecked}"


# --- FastAPI async handlers, reported against 0.15.2 ------------------------


def test_no_route_handler_is_async_without_awaiting() -> None:
    """SonarQube: "Use asynchronous features in this function or remove the
    `async` keyword."

    Four findings on 0.15.2, all in `object_lists.py`, and the rest of the
    route modules carry the same shape. They were not reported only because
    the gate counts new issues, so every one of them is a failure waiting for
    its file to be edited.

    It is not only a smell. An `async def` handler runs on the event loop, so
    a blocking store read or write holds every other request. A plain `def`
    handler runs in a threadpool, which is what this application actually
    wants.

    **Scoped to `src` on purpose, and this is the one over-fire correction
    made when the mirror was calibrated.** The test doubles in
    `tests/conftest.py` stand in for the UDL client's async interface and are
    awaited by the code under test, so they must stay `async` and cannot be
    fixed. The platform has only ever reported this rule in `src/routes/`. If
    it ever reports it against a test double, that is a new register entry
    and a different problem: a mirror demanding an unfixable change is worse
    than no mirror.
    """
    offenders = []
    for path in _python_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            awaits = any(
                isinstance(inner, (ast.Await, ast.AsyncFor, ast.AsyncWith))
                for inner in ast.walk(node)
            )
            if not awaits:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.name}")
    assert offenders == [], f"Drop the async keyword or await something: {offenders}"


# --- Shell nesting, reported against 0.15.3 ---------------------------------


def _matching_fi(lines: list[str], start: int) -> int:
    """Index of the `fi` closing the `if` that opens at `start`, or -1."""
    depth = 0
    for index in range(start, len(lines)):
        stripped = lines[index].strip()
        if re.match(r"^(if|elif)\b", stripped) and stripped != "elif":
            depth += 1 if stripped.startswith("if") else 0
        if stripped == "fi" or stripped.startswith("fi "):
            depth -= 1
            if depth == 0:
                return index
    return -1


def _meaningful(lines: list[str], first: int, last: int) -> list[int]:
    """Line indices in a body, skipping blanks and comments."""
    return [
        index
        for index in range(first, last)
        if lines[index].strip() and not lines[index].strip().startswith("#")
    ]


def _only_wraps_an_if(lines: list[str], index: int) -> int | None:
    """The inner `if`'s index when the `if` at `index` holds nothing else.

    Returns None unless the outer block's whole body is one inner `if` and
    the outer carries no `else` or `elif` of its own. With an `else` the
    nesting is doing real work and the rule does not fire.
    """
    if not re.match(r"^\s*if\b", lines[index]):
        return None
    closing = _matching_fi(lines, index)
    if closing == -1:
        return None
    body = _meaningful(lines, index + 1, closing)
    if not body or not re.match(r"^\s*if\b", lines[body[0]]):
        return None
    inner_close = _matching_fi(lines, body[0])
    if inner_close != body[-1]:
        return None
    outer_branches = [
        number
        for number in body
        if re.match(r"^\s*(else|elif)\b", lines[number])
        and not body[0] < number < inner_close
    ]
    return None if outer_branches else body[0]


def test_no_shell_if_wraps_only_another_if() -> None:
    """SonarQube: "Merge this if statement with the enclosing one."

    Reported against 0.15.3, in `bump_version.sh`, where an outer `if` did
    nothing but hold an inner one. Two conditions that must both hold read as
    one `&&`, and writing them nested invites an `else` later that silently
    attaches to the wrong branch.

    Only fires when the outer has no `else` or `elif` of its own, because
    then the nesting really is carrying nothing.
    """
    offenders = []
    for path in _shell_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        for index in range(len(lines)):
            inner = _only_wraps_an_if(lines, index)
            if inner is not None:
                offenders.append(f"{path.relative_to(ROOT)}:{inner + 1}")
    assert offenders == [], f"Merge the nested if with its enclosing one: {offenders}"
