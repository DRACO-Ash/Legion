#!/usr/bin/env bash
# Bumps the version consistently across src/VERSION, CHANGELOG.md, and a
# git tag, so the artifact stamp, the running app's /version endpoint, and
# the App Store submission's "App Details" version field can never drift
# apart (packaging: "normalise the version" before packaging).
#
# Usage: scripts/bump_version.sh <new_version> "<changelog summary line>"
# Example: scripts/bump_version.sh 0.4.0 "Add elset caching"

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <new_version> \"<changelog summary>\"" >&2
  exit 1
fi

NEW_VERSION="$1"
SUMMARY="$2"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION_FILE="$REPO_ROOT/src/VERSION"
CHANGELOG_FILE="$REPO_ROOT/CHANGELOG.md"

if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: '$NEW_VERSION' is not a plain semver (MAJOR.MINOR.PATCH)." >&2
  exit 1
fi

if [ ! -d "$REPO_ROOT/.git" ]; then
  echo "Error: no git repository at $REPO_ROOT. Run 'git init' first." >&2
  exit 1
fi

if [ -n "$(git -C "$REPO_ROOT" status --porcelain)" ] && [ -n "$(git -C "$REPO_ROOT" status --porcelain -- . ':!src/VERSION' ':!CHANGELOG.md' ':!pyproject.toml')" ]; then
  echo "Error: working tree has uncommitted changes beyond VERSION/CHANGELOG. Commit or stash first." >&2
  exit 1
fi

CURRENT_VERSION="$(cat "$VERSION_FILE" 2>/dev/null || echo "none")"
TODAY="$(date -u +%Y-%m-%d)"

# Warn when a release changes nothing under sonar.sources. The App Store's
# code-quality-verify job fails a build for which SonarQube measured no
# coverage, and it measures coverage only on changed files inside
# sonar.sources (src). A docs-only or Dockerfile-only release therefore fails
# that job every time and no number of retries changes it, because there is
# nothing to measure. This is a warning, not a block: such a release is
# legitimate, but it needs to be bundled with a source change or held until
# the platform treats "nothing analysed" as a pass. See CLAUDE.md, "The Code
# Quality gate has five conditions".
PREV_TAG="v$CURRENT_VERSION"
if git -C "$REPO_ROOT" rev-parse -q --verify "$PREV_TAG" >/dev/null 2>&1; then
  if [ -z "$(git -C "$REPO_ROOT" diff --name-only "$PREV_TAG" HEAD -- 'src/**.py' 'src/*.py')" ]; then
    echo "WARNING: no Python file under src/ has changed since $PREV_TAG." >&2
    echo "         SonarQube measures coverage on new code, so if $PREV_TAG is" >&2
    echo "         what the App Store already holds, code-quality-verify will" >&2
    echo "         fail with 'coverage was not measured for this build'." >&2
    echo "         Baseline caveat: this compares against the last LOCAL tag." >&2
    echo "         The gate compares against the deployment repository's main." >&2
    echo "         If $PREV_TAG never merged, its source changes are still in" >&2
    echo "         the diff the gate sees and this warning does not apply." >&2
    echo "         Check what actually merged before acting on it." >&2
    echo "         Do not pipe this script through head or tail: that is how" >&2
    echo "         this warning got lost once already." >&2
  fi
fi

echo -n "$NEW_VERSION" > "$VERSION_FILE"

TMP_CHANGELOG="$(mktemp)"
{
  head -n 6 "$CHANGELOG_FILE"
  echo ""
  echo "## [$NEW_VERSION] - $TODAY"
  echo ""
  echo "$SUMMARY"
  echo ""
  tail -n +7 "$CHANGELOG_FILE"
} > "$TMP_CHANGELOG"
mv "$TMP_CHANGELOG" "$CHANGELOG_FILE"

# pyproject.toml carries the version too (it pairs with requirements.txt for
# the Dependency Scanning analyser). Keep it in step here rather than by hand.
PYPROJECT_FILE="$REPO_ROOT/pyproject.toml"
if [ -f "$PYPROJECT_FILE" ]; then
  python3 - "$PYPROJECT_FILE" "$NEW_VERSION" <<'PY'
import re, sys
path, version = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
new, count = re.subn(r'(?m)^version = ".*"$', f'version = "{version}"', text, count=1)
if count != 1:
    sys.exit(f"Error: could not find a single version line in {path}")
open(path, "w", encoding="utf-8").write(new)
PY
  git -C "$REPO_ROOT" add pyproject.toml
fi

git -C "$REPO_ROOT" add src/VERSION CHANGELOG.md
git -C "$REPO_ROOT" commit -m "Bump version: $CURRENT_VERSION -> $NEW_VERSION

$SUMMARY"
git -C "$REPO_ROOT" tag -a "v$NEW_VERSION" -m "$SUMMARY"

echo "Bumped $CURRENT_VERSION -> $NEW_VERSION, committed, and tagged v$NEW_VERSION."
echo "Push with: git push && git push --tags"
