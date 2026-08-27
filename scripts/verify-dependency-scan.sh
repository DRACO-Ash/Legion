#!/usr/bin/env bash
# Runs GitLab's dependency-scanning analyser against a built package, so the
# Dependency Scanning gate can be checked before an upload rather than after.
#
# Why this exists: the platform maps any non-zero analyser exit to "Vulnerable
# dependencies found" and uploads no report, so a crashed scan is presented as
# a finding with no error text. The analyser is open source, so run it here and
# read the message the platform swallows.
#
# Usage: scripts/verify-dependency-scan.sh [package-dir]
#        DS_ANALYZER_BIN=/path/to/binary  reuse a prebuilt analyser
#
# Requires Go and network access to gitlab.com and proxy.golang.org.
#
# CAVEAT, read before trusting a pass: as of 27 August 2026 the Bluestaq
# pipeline runs an analyser identifying itself as "dependency-scan-python
# v6.6.1", which prints a line ("Dependency files in other directories will be
# skipped") that does not exist anywhere in this codebase. This script
# therefore checks a closely related analyser, not the exact one the platform
# runs. A pass here means the package parses and produces a valid SBOM; it is
# not proof the platform's gate will pass.

set -euo pipefail

PACKAGE_DIR="${1:-.}"
REPO="https://gitlab.com/gitlab-org/security-products/analyzers/dependency-scanning.git"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [ -n "${DS_ANALYZER_BIN:-}" ]; then
  ANALYZER="$DS_ANALYZER_BIN"
else
  echo "Cloning and building the analyser (this takes a few minutes)..."
  git clone --depth 1 -q "$REPO" "$WORK/src"
  (cd "$WORK/src" && GOFLAGS=-mod=mod go build -o "$WORK/analyzer" ./cmd/...)
  ANALYZER="$WORK/analyzer"
fi

# The analyser needs a git repository: it resolves input-file alternatives
# through `git ls-files`, and needs the licence feature flag set.
cp -a "$PACKAGE_DIR" "$WORK/pkg"
cd "$WORK/pkg"
rm -rf .git
git init -q .
git add -A
git -c user.email=verify@local -c user.name=verify commit -qm "package under test"

set +e
GITLAB_FEATURES=dependency_scanning SECURE_LOG_LEVEL=debug "$ANALYZER" run 2>&1 \
  | grep -E "\[(WARN|ERRO|FATA)\]|generated SBOM|component count"
status=${PIPESTATUS[0]}
set -e

if [ "$status" -ne 0 ]; then
  echo "FAIL: analyser exited $status. The platform would report this as"
  echo "      'Vulnerable dependencies found' with no report attached."
  exit 1
fi

sbom=$(ls gl-sbom-*.cdx.json 2>/dev/null | head -1 || true)
if [ -z "$sbom" ]; then
  echo "FAIL: analyser exited 0 but produced no SBOM. The gate needs one."
  exit 1
fi

echo "PASS: exit 0, SBOM $sbom written."
python3 -c "import json,sys; d=json.load(open('$sbom')); print('      components:', len(d.get('components', [])), 'graph entries:', len(d.get('dependencies', [])))"
