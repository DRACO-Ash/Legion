#!/usr/bin/env bash
# Everything the Code Quality gate can be checked for locally, in one command.
#
# Run this before packaging. It is not a guarantee: two gate conditions have
# no local check (duplicated lines on new code, and security hotspots needing
# human review), and it says so at the end rather than implying otherwise.
#
# docs/SONAR-RULE-REGISTER.md is the index of what is covered and why.
#
# Every tool runs through one resolved interpreter, and the run stops if that
# interpreter cannot import the application. A checker that silently falls
# back to whatever is on PATH reports on a different installation than the one
# under test, which is a false verdict rather than a missing one.
set -uo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-}"
if [[ -z "$PY" ]]; then
  if [[ -x .venv/bin/python ]]; then PY=.venv/bin/python; else PY=python3; fi
fi
echo "Interpreter: $("$PY" -c 'import sys; print(sys.executable, sys.version.split()[0])')"

missing=""
for module in pytest ruff mypy bandit fastapi; do
  "$PY" -c "import $module" 2>/dev/null || missing="$missing $module"
done
if [[ -n "$missing" ]]; then
  echo
  echo "This interpreter cannot import:$missing"
  echo "Activate the project venv, or run: PYTHON=/path/to/python $0"
  echo "Refusing to check a different installation than the one under test."
  exit 2
fi

fail=0
run() {
  local label="$1"
  shift
  printf '\n=== %s ===\n' "$label"
  if "$@"; then :; else fail=1; fi
  return 0
}

run "SonarQube rule mirrors" \
  "$PY" -m pytest tests/test_sonar_contracts.py tests/test_sonar_platform_rules.py \
                  tests/test_sonar_cognitive_complexity.py -q
run "Interface contracts" "$PY" -m pytest tests/test_ui_contracts.py -q
run "Full suite with coverage" "$PY" -m pytest -q --cov=src --cov-report=term:skip-covered
run "Lint" "$PY" -m ruff check src tests
run "Format" "$PY" -m ruff format --check src tests
run "Types" "$PY" -m mypy src
run "Security" "$PY" -m bandit -q -r src

printf '\n========================================================\n'
if [[ "$fail" -ne 0 ]]; then
  echo "FAIL. Fix the above before packaging."
  exit 1
fi
cat <<'NOTE'
PASS on every condition that can be checked from here.

Two gate conditions still cannot be checked locally:
  - Duplicated lines on new code. Keep shared fixtures in tests/conftest.py.
  - Security hotspots reviewed. A person must review these in SonarQube.
And one process condition: the release must change a Python file under
sonar.sources (src), or coverage is unmeasurable and code-quality-verify
fails. bump_version.sh REFUSES such a bump; --allow-unmeasurable overrides.
NOTE
