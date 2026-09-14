#!/usr/bin/env bash
# Bumps the version consistently across src/VERSION, CHANGELOG.md, and a
# git tag, so the artifact stamp, the running app's /version endpoint, and
# the App Store submission's "App Details" version field can never drift
# apart (packaging: "normalise the version" before packaging).
#
# Usage: scripts/bump_version.sh <new_version> "<changelog summary line>"
# Example: scripts/bump_version.sh 0.4.0 "Add elset caching"

set -euo pipefail

# --allow-unmeasurable: proceed even when the release changes no Python under
# src. Stripped here so the positional arguments stay where they were.
ALLOW_UNMEASURABLE=0
ARGS=()
for arg in "$@"; do
  if [[ "$arg" == "--allow-unmeasurable" ]]; then
    ALLOW_UNMEASURABLE=1
  else
    ARGS+=("$arg")
  fi
done
set -- "${ARGS[@]+"${ARGS[@]}"}"

if [[ $# -lt 2 ]]; then
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

if [[ ! -d "$REPO_ROOT/.git" ]]; then
  echo "Error: no git repository at $REPO_ROOT. Run 'git init' first." >&2
  exit 1
fi

if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" && -n "$(git -C "$REPO_ROOT" status --porcelain -- . ':!src/VERSION' ':!CHANGELOG.md' ':!pyproject.toml')" ]]; then
  echo "Error: working tree has uncommitted changes beyond VERSION/CHANGELOG. Commit or stash first." >&2
  exit 1
fi

CURRENT_VERSION="$(cat "$VERSION_FILE" 2>/dev/null || echo "none")"
TODAY="$(date -u +%Y-%m-%d)"

# Refuse a release that changes nothing under sonar.sources. The App Store's
# code-quality-verify job fails a build for which SonarQube measured no
# coverage, and it measures coverage only on changed files inside
# sonar.sources (src). A docs-only, tests-only or script-only release fails
# that job every time and no number of retries changes it, because there is
# nothing to measure. See CLAUDE.md, "The Code Quality gate has five
# conditions".
#
# This was a warning until 0.15.5 and a warning was not enough: 0.15.4 was cut
# in exactly this state and the warning was missed because the output was
# piped through tail. A condition that no retry can clear should not be
# possible to ship by accident, so it now stops the bump. Pass
# --allow-unmeasurable to proceed anyway, which makes it a decision somebody
# made rather than something nobody saw.
PREV_TAG="v$CURRENT_VERSION"
if [[ "$ALLOW_UNMEASURABLE" != "1" ]] \
   && git -C "$REPO_ROOT" rev-parse -q --verify "$PREV_TAG" >/dev/null 2>&1 \
   && [[ -z "$(git -C "$REPO_ROOT" diff --name-only "$PREV_TAG" HEAD -- 'src/**.py' 'src/*.py')" ]]; then
  echo "REFUSING: no Python file under src/ has changed since $PREV_TAG." >&2
  echo "" >&2
  echo "  SonarQube measures coverage on new code. With nothing changed inside" >&2
  echo "  sonar.sources (src), it measures no coverage at all, and the App" >&2
  echo "  Store's code-quality-verify job fails the build with 'coverage was" >&2
  echo "  not measured for this build'. Retrying cannot help." >&2
  echo "" >&2
  echo "  Either bundle this with a real source change, or re-run with" >&2
  echo "  --allow-unmeasurable if you know this release will not be uploaded." >&2
  echo "" >&2
  echo "  Baseline caveat: this compares against the last LOCAL tag. The gate" >&2
  echo "  compares against the deployment repository's main. If $PREV_TAG" >&2
  echo "  never merged, its source changes are still in the diff the gate" >&2
  echo "  sees and this does not apply. Check what actually merged." >&2
  exit 1
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
if [[ -f "$PYPROJECT_FILE" ]]; then
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
