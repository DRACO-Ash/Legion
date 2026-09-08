"""A local mirror of SonarQube python:S3776, cognitive complexity.

The gate rejected 0.6.0 for two functions at 25 and 18 against a limit of 15.
This reproduces Sonar's measure rather than guessing at it, so the next
refactor can be checked before an upload rather than after one.

Calibration, against the exact numbers the platform reported for 0.6.0:
`build_family_charts` measured 25 here and 25 there; `build_series` 18 and 18,
at the same line numbers. That is two matching data points, not a proof, so
the local budget below sits one point under the platform's 15.

The algorithm follows Sonar's white paper. A structure that can nest -
`if`, a ternary, a loop, an `except` handler - scores one plus the current
nesting depth. A structure that cannot - `elif`, `else` - scores one flat. A
sequence of boolean operators scores one. Nested functions and lambdas add
depth without scoring themselves.
"""

from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCANNED_TREES = (ROOT / "src", ROOT / "tests")

# The platform allows 15. One point of margin covers a construct this mirror
# might weigh differently, because a failed upload costs a cycle and moving a
# branch into a named helper costs minutes.
MAX_COGNITIVE_COMPLEXITY = 14


class _Cognitive(ast.NodeVisitor):
    def __init__(self) -> None:
        self.score = 0
        self.nesting = 0

    def _structure(self, count_nesting: bool = True) -> None:
        self.score += 1 + (self.nesting if count_nesting else 0)

    def _deeper(self, nodes: list[ast.stmt]) -> None:
        self.nesting += 1
        for node in nodes:
            self.visit(node)
        self.nesting -= 1

    def visit_If(self, node: ast.If) -> None:
        self._structure()
        self.visit(node.test)
        self._deeper(node.body)
        self._visit_else(node.orelse)

    def _visit_else(self, orelse: list[ast.stmt]) -> None:
        while orelse:
            # A lone If in an else branch is an elif: flat one, no depth.
            if len(orelse) == 1 and isinstance(orelse[0], ast.If):
                branch = orelse[0]
                self._structure(count_nesting=False)
                self.visit(branch.test)
                self._deeper(branch.body)
                orelse = branch.orelse
            else:
                self._structure(count_nesting=False)
                self._deeper(orelse)
                return

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._structure()
        self.nesting += 1
        self.generic_visit(node)
        self.nesting -= 1

    def _loop(self, node: ast.For | ast.AsyncFor | ast.While) -> None:
        self._structure()
        if isinstance(node, ast.While):
            self.visit(node.test)
        self._deeper(node.body)
        if node.orelse:
            self._structure(count_nesting=False)
            self._deeper(node.orelse)

    def visit_For(self, node: ast.For) -> None:
        self._loop(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._loop(node)

    def visit_While(self, node: ast.While) -> None:
        self._loop(node)

    def visit_Try(self, node: ast.Try) -> None:
        for statement in [*node.body, *node.orelse, *node.finalbody]:
            self.visit(statement)
        for handler in node.handlers:
            self._structure()
            self._deeper(handler.body)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self._structure(count_nesting=False)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._deeper(node.body)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._deeper(node.body)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.nesting += 1
        self.visit(node.body)
        self.nesting -= 1


def cognitive_complexity(function: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    visitor = _Cognitive()
    for statement in function.body:
        visitor.visit(statement)
    return visitor.score


def _functions() -> list[tuple[pathlib.Path, ast.FunctionDef | ast.AsyncFunctionDef]]:
    found = []
    for tree in SCANNED_TREES:
        for path in sorted(tree.rglob("*.py")):
            parsed = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(parsed):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    found.append((path, node))
    return found


def test_no_function_exceeds_the_cognitive_complexity_budget() -> None:
    """SonarQube python:S3776."""
    offenders = {
        f"{path.relative_to(ROOT)}:{node.lineno} {node.name}": score
        for path, node in _functions()
        if (score := cognitive_complexity(node)) > MAX_COGNITIVE_COMPLEXITY
    }
    assert offenders == {}, (
        f"Extract a helper to bring these under {MAX_COGNITIVE_COMPLEXITY}: {offenders}"
    )


def test_the_mirror_reproduces_a_known_score() -> None:
    """Guards the measure itself.

    The case below comes to 13, worked through against the white paper. Note
    the two columns the paper keeps apart: `else` and `elif` score a flat one
    rather than one-plus-depth, but they still deepen the nesting for whatever
    sits inside them, which is why the ternary in the else costs four. If a
    change to the visitor moves this number, the mirror has stopped measuring
    what the platform measures.
    """
    source = """
def sample(rows, flag):
    for row in rows:                     # +1, running 1
        for cell in row:                 # +2 at depth 1, running 3
            if cell and flag:            # +3 at depth 2, running 6
                return 1                 # and +1 for "and", running 7
            elif cell:                    # +1 flat, running 8
                return 2
            else:                         # +1 flat, running 9
                return 3 if flag else 4   # +4 ternary at depth 3, running 13
    return 0
"""
    function = ast.parse(source).body[0]
    assert isinstance(function, ast.FunctionDef)
    assert cognitive_complexity(function) == 13
