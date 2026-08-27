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
# CALIBRATION RESULT, READ THIS BEFORE TRUSTING ANY VERDICT HERE.
#
# This script does NOT predict the platform's gate. It was calibrated on 27
# August 2026 against three packages whose real outcomes are known, and it was
# wrong on two of them:
#
#   package                platform gate     this script
#   PSIRENS 1.5.3          PASSED            exit 1, no SBOM
#   Enlightenment 0.23.3   PASSED            exit 0, 27 components
#   Legion 0.4.3           FAILED            exit 0, 57 components
#
# The cause is that the Bluestaq pipeline runs an analyser identifying itself
# as "dependency-scan-python v6.6.1", which prints a line ("Dependency files in
# other directories will be skipped") that exists nowhere in the open-source
# dependency-scanning codebase this script builds (HEAD is v2.5.9). Different
# tool, different verdict.
#
# So use this only as a DIAGNOSTIC: it prints the parse warnings and the SBOM
# the platform swallows, which is useful for understanding how a package is
# being classified. Never treat a pass here as evidence the gate will pass, and
# never treat a failure here as a reason to change a package.

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
  echo "DIAGNOSTIC ONLY (see header): analyser exited $status."
  echo "      This does NOT mean the platform gate will fail."
  exit 1
fi

sbom=$(ls gl-sbom-*.cdx.json 2>/dev/null | head -1 || true)
if [ -z "$sbom" ]; then
  echo "FAIL: analyser exited 0 but produced no SBOM. The gate needs one."
  exit 1
fi

echo "DIAGNOSTIC ONLY (see header): exit 0, SBOM $sbom written."
python3 -c "import json,sys; d=json.load(open('$sbom')); print('      components:', len(d.get('components', [])), 'graph entries:', len(d.get('dependencies', [])))"
