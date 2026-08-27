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
