#!/usr/bin/env bash
# Build an App Store upload package, and refuse to build one that will fail.
#
# One command between a tag and a zip, so the checks cannot be skipped by
# forgetting them. It does four things in order, and stops at the first that
# fails:
#
#   1. Runs every local gate check (scripts/check-quality-gate.sh).
#   2. Confirms the release changes a Python file under sonar.sources, which
#      is the one gate condition no retry can clear.
#   3. Builds the zip from the tag, never from the working tree.
#   4. Extracts it and runs the suite from the extracted archive, which is
#      what proves nothing that ships depends on an export-ignored file.
#
# Step 4 is the one that is easy to skip and the one that has caught most.
# reference/satcat_26195.dat is export-ignored, so an import of it would pass
# every test in the working tree and fail in the container.
#
# Usage: scripts/package.sh [vX.Y.Z]     (defaults to the tag for src/VERSION)
set -uo pipefail
cd "$(dirname "$0")/.."

REPO_ROOT="$(pwd)"
VERSION="$(cat src/VERSION)"
TAG="${1:-v$VERSION}"
OUT_DIR="${PACKAGE_OUT_DIR:-$REPO_ROOT/dist}"

step() {
  local label="$1"
  printf '\n\033[1m=== %s ===\033[0m\n' "$label"
  return 0
}

# Prints and returns rather than exiting, so it ends in an explicit return.
# The caller exits. Whether SonarQube exempts a function whose last statement
# is `exit` is not established, and the register's rule is not to guess: the
# shape is avoided instead of the mirror being widened on a hunch.
fail() {
  local message="$1"
  printf '\n\033[31mREFUSING: %s\033[0m\n' "$message" >&2
  return 1
}

step "Tag"
if ! git rev-parse -q --verify "$TAG" >/dev/null 2>&1; then
  fail "no such tag: $TAG. Cut one with scripts/bump_version.sh first."
  exit 1
fi
TAGGED_VERSION="$(git show "$TAG:src/VERSION" 2>/dev/null || echo "")"
if [[ "$TAGGED_VERSION" != "$VERSION" ]]; then
  fail "$TAG holds version '$TAGGED_VERSION' but src/VERSION says '$VERSION'."
  exit 1
fi
echo "$TAG, version $VERSION"

step "Working tree"
if [[ -n "$(git status --porcelain)" ]]; then
  fail "uncommitted changes. The package is built from the tag, so anything
  uncommitted would not be in it and you would be testing the wrong thing."
  exit 1
fi
echo "clean"

# Every local gate condition. This is the expensive step and it comes early on
# purpose: a package that fails it should never be built at all.
if ! ./scripts/check-quality-gate.sh; then
  fail "local gate checks failed. Fix those before building a package."
  exit 1
fi

step "Coverage measurability"
# The gate condition with no error message worth reading and no retry that
# helps. See CLAUDE.md, "The Code Quality gate has five conditions".
PREV_TAG="$(git tag --sort=-v:refname | grep -A1 -x "$TAG" | tail -1)"
if [[ -z "$PREV_TAG" || "$PREV_TAG" == "$TAG" ]]; then
  echo "no earlier tag to compare against, skipping"
elif [[ -z "$(git diff --name-only "$PREV_TAG" "$TAG" -- 'src/**.py' 'src/*.py')" ]]; then
  fail "no Python file under src/ changed between $PREV_TAG and $TAG.
  SonarQube would measure no coverage and code-quality-verify would fail the
  build. Bundle a real source change, or upload knowing this will fail."
  exit 1
else
  echo "changed since $PREV_TAG:"
  git diff --name-only "$PREV_TAG" "$TAG" -- 'src/**.py' 'src/*.py' | sed 's/^/  /'
fi

step "Build"
mkdir -p "$OUT_DIR"
ZIP="$OUT_DIR/legion-$VERSION.zip"
rm -f "$ZIP"
if ! git archive --format=zip --prefix="legion-$VERSION/" -o "$ZIP" "$TAG"; then
  fail "git archive failed"
  exit 1
fi
echo "$ZIP ($(du -h "$ZIP" | cut -f1))"

step "Package contract"
# The shape the Dependency Scanning analyser needs, per the appstore-python-gate
# skill. Absence of the root pyproject.toml is the single highest-value
# difference between the packages that clear the gate and the one that did not.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
if ! unzip -q "$ZIP" -d "$WORK"; then
  fail "could not extract the package just built"
  exit 1
fi
PKG="$WORK/legion-$VERSION"
missing=""
for required in pyproject.toml requirements.txt requirements-runtime.txt Dockerfile src/VERSION; do
  if [[ ! -f "$PKG/$required" ]]; then
    missing="$missing $required"
  fi
done
if [[ -n "$missing" ]]; then
  fail "the package is missing:$missing"
  exit 1
fi
if ! grep -q '^\[project\]' "$PKG/pyproject.toml"; then
  fail "pyproject.toml carries no [project] table. Dependency Scanning needs one."
  exit 1
fi
if [[ -e "$PKG/.gitlab-ci.yml" ]]; then
  fail ".gitlab-ci.yml is in the package. It belongs in the GitLab repository,
  and a version upload does not update it there. See CLAUDE.md."
  exit 1
fi
echo "root files present, [project] table present, no .gitlab-ci.yml"

step "The archive tests itself"
# Not the working tree. reference/satcat_26195.dat is export-ignored, so this
# is the only step that would catch a dependency on a file that does not ship.
PY="${PYTHON:-}"
if [[ -z "$PY" ]]; then
  if [[ -x .venv/bin/python ]]; then PY="$REPO_ROOT/.venv/bin/python"; else PY=python3; fi
fi
if ! (cd "$PKG" && "$PY" -m pytest -q --cov=src --cov-report=term:skip-covered); then
  fail "the extracted package fails its own tests. Something that ships depends
  on a file that does not."
  exit 1
fi

printf '\n\033[32m========================================================\033[0m\n'
echo "Package ready: $ZIP"
echo "Built from $TAG, extracted and tested from the archive itself."
echo ""
echo "Still not checked here, because nothing local can:"
echo "  - Duplicated lines on new code. Shared fixtures live in tests/conftest.py."
echo "  - Security hotspots reviewed. A person reviews those in SonarQube."
echo "  - Whether the GitLab .gitlab-ci.yml is current. A version upload does"
echo "    not update it; that needs a direct commit to the GitLab repository."
