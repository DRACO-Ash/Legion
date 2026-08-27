# Dependency Scanning: passing the Bluestaq App Store gate

**Portable reference. Written for Python container apps, 27 August 2026.**
Distilled from an investigation that cost Legion four upload cycles, then
resolved by comparing against two applications known to clear the gate.

Fuse this into any App Store project. It is written to be read by whoever is
about to submit, and by an AI assistant asked to fix a Dependency Scanning
failure. The fastest possible summary is one line:

> **A Dependency Scanning failure almost certainly does not mean you have a
> vulnerable dependency. It usually means the analyser crashed while working
> out what your dependency files are, and the platform relabelled a non-zero
> exit code as "Vulnerable dependencies found".**

Everything below exists to stop you spending days upgrading packages that were
never flagged.

## How to read the confidence markers

This project's house discipline separates what was verified from what was
reasoned. Every claim here is marked:

● **FACT** means observed directly, in a real pipeline run or by running the
  code. Trust it.
● **INFERENCE** means reasoned from the analyser's open source or from control
  samples, and consistent with everything observed, but not proven against the
  platform's own binary.
● **UNKNOWN** means honestly not established. Do not let anyone quietly promote
  these to fact.

## 1. What the gate actually does

● **FACT.** The Bluestaq pipeline runs an analyser that identifies itself in
  the job log as `dependency-scan-python`, version 6.6.1. It executes
  `/analyzer run` against the repository root.
● **FACT.** On success it writes two artefacts, `gl-sbom-*.cdx.json` (a
  CycloneDX Software Bill of Materials, or SBOM) and
  `gl-dependency-scanning-report.json`.
● **FACT.** On the failures observed, the job log contains exactly two INFO
  lines, then `exit status 1` after roughly eight seconds, with **no error
  text at all**, followed by `WARNING: ... no matching files` for both
  artefacts.
● **FACT.** The App Store user interface renders any non-zero exit as
  "Vulnerable dependencies found. Update the flagged dependencies to versions
  without known vulnerabilities." No dependency is named, because none was
  flagged.

**The single most useful diagnostic signal:**

● **INFERENCE (from the analyser's open source).** SBOM generation happens
  *before* the vulnerability lookup. So if the failed job produced **no SBOM
  artefact**, the analyser died while parsing or classifying your dependency
  files, and never reached the stage where it compares anything against an
  advisory database. If it produced an SBOM *and* failed, then and only then
  should you look at actual package versions.

Check this first. It splits the problem in half.

## 2. The evidence

Three packages, all Python container apps for the same App Store, with their
real gate outcomes:

| Application | Gate | `pyproject.toml` | `requirements.txt` header | Hashes | `.in` files |
|---|---|---|---|---|---|
| PSIRENS 1.5.3 | **Passed** | yes | hand-written banner | none | none |
| Enlightenment 0.23.3 | **Passed** | yes | uv header, line 1 | yes | yes, three pairs |
| Legion 0.4.3 | **Failed** | **no** | pip-compile header, line 2 | yes | yes, two pairs |

● **FACT.** A file-level comparison of the three package roots found that
  `pyproject.toml` is the **only** file present in both passing packages and
  absent from the failing one. Every other difference was documentation.

## 3. The checklist

Run through this before any submission. Items are ordered by how much pain
they have actually caused.

### 3.1 Ship a `pyproject.toml` at the package root

● **INFERENCE, strongest available.** Both known-passing applications ship one.
  The failing one did not. The analyser's pip-tools package manager treats
  `requirements.txt` as a *lockfile* and expects a *requirements-type* file
  alongside it; `pyproject.toml` is the one both passers supply.

Copy this, change the three values, add nothing else:

```toml
[project]
name = "your-app"
version = "0.1.0"
description = "One line, plain English."
requires-python = ">=3.12"
```

Deliberately **no** `[project.dependencies]` list. Neither passing application
declares one. Dependencies belong in your pip-compile inputs and their locked
outputs, which is what the platform's test stage and your Dockerfile actually
install. Declaring them twice lets the two drift, and drift is what the gate
punishes.

Keep the version in step with your single source of truth automatically. If you
have a `bump_version.sh`, have it rewrite that line; never edit it by hand.

Be aware of one side effect: declaring `requires-python` may tighten the target
version your linter infers, which can surface new lint findings. Fix them, do
not suppress them.

### 3.2 Know which filenames the analyser can even see

● **INFERENCE (read from the open-source sibling analyser; the platform's build
  is very likely the same table, but this was not confirmed against v6.6.1).**

For Python, only these names are registered:

| Package manager | Files it recognises |
|---|---|
| pip | `requirements.txt`, `requirements.pip`, `requires.txt`, `pipdeptree.json` |
| pip-tools | `requirements.txt` (lockfile), `pipcompile.lock.txt` (lockfile), `pyproject.toml`, `setup.cfg`, `setup.py`, `requirements.in` |
| poetry | `pyproject.toml`, `poetry.lock` |
| uv | `pyproject.toml`, `uv.lock` |
| setuptools | `setup.py`, `pipdeptree.json` |

Two consequences worth internalising:

● Files such as `requirements-runtime.txt`, `requirements-dev.txt` and
  `requirements-runtime.in` are **not registered names**. The analyser does not
  read them. You cannot fix a scan failure by editing them, and they cannot
  cause one either. Both passing applications ship extra `requirements-*.txt`
  files with plain hand-written headers and pass regardless.
● Only the repository root is scanned by default. **FACT:** the job log states
  "Dependency files in other directories will be skipped", and `DS_MAX_DEPTH`
  defaults to 2. Moving a file into a subdirectory removes it from the scan.

### 3.3 Do not chase the lockfile header

● **FACT.** PSIRENS passes with a `requirements.txt` that opens with a
  hand-written comment banner and contains 21 pinned packages and **no hashes
  at all**. Enlightenment passes with a uv-generated header on line 1. Legion
  failed with a valid pip-compile header on line 2.

Three different header forms, two passes and one failure. The header form does
not predict the outcome. If a document or an assistant tells you the fix is to
regenerate `requirements.txt` so its header sits on the right line, that advice
is derived from a different codebase and does not generalise. Verify before
acting on it.

Hash-locking is good practice for supply-chain integrity and you should keep
it. It is simply not what this gate is failing on.

### 3.4 Keep the package root flat and conventional

● **FACT, from an earlier failure on the same app.** The container template is
  detected from a root-level `Dockerfile`. A nested one breaks both template
  detection and the build context.

Ship a testable source tree: the platform's test stage runs
`pip install -r requirements.txt` then `pytest` against the package root before
it builds any image, so `tests/` and your test configuration must be inside the
package, even though `.dockerignore` keeps them out of the image. Those are two
separate contracts.

Neither passing application ships a `.gitlab-ci.yml` inside the package. That
file lives in the deployment repository and a version upload does not update
it. Shipping a copy is at best inert.

### 3.5 Prove the dependency set really is clean, separately

The gate will not tell you, so establish it yourself and keep the evidence:

● Run your language's audit tool against the exact locked file the image
  installs (`pip-audit -r requirements.txt`).
● Confirm your build reproduces from the lockfile in a clean environment, on
  the same interpreter version the platform uses.

If both are clean and the gate still fails, you have a tooling failure, not a
security finding, and you should say so plainly rather than start upgrading
packages at random.

## 4. What is not the cause

Ruled out by direct evidence. Do not spend a cycle on any of these:

● **An actual vulnerable package.** No report artefact was ever produced, so
  nothing was ever flagged.
● **The lockfile header form.** See 3.3.
● **Missing hashes, or having hashes.** Both extremes pass.
● **Having several `requirements-*.in` and `.txt` pairs.** Enlightenment ships
  three pairs and passes.
● **The Python version floor.** The passing pair declare `>=3.11` and
  `>=3.12,<3.13` respectively.

## 5. Diagnosing a failure

In order, cheapest first:

1. **Look for the SBOM artefact.** No SBOM means a parse or classification
   crash, not a vulnerability. See section 1.
2. **Compare your package root against a known-passing package.** This is the
   single highest-value diagnostic available and it took four cycles to think
   of. Get a colleague's passing zip, list both roots, and diff the filenames.
   That one comparison produced the answer where source-reading had not.
3. **Get the real error text.** The platform swallows the analyser's stderr.
   Either use the "More Details" link on the failed gate in the App Store user
   interface, or have whoever owns the deployment repository re-run with
   `SECURE_LOG_LEVEL=debug` set in the pipeline file.
4. **Only then consider the escape hatches** in section 6.

### The trap: do not trust a locally built analyser

● **FACT.** GitLab's open-source `dependency-scanning` analyser can be cloned
  and built with Go, and run against a package. Doing so is genuinely useful
  for reading the parse warnings the platform hides.
● **FACT.** It is **not** the platform's analyser, and its verdict is actively
  misleading. Calibrated against the three packages above, it was wrong on two:

| Package | Platform gate | Locally built analyser |
|---|---|---|
| PSIRENS 1.5.3 | Passed | exit 1, no SBOM |
| Enlightenment 0.23.3 | Passed | exit 0, 27 components |
| Legion 0.4.3 | Failed | exit 0, 57 components |

The platform's analyser prints a line ("Dependency files in other directories
will be skipped") that exists nowhere in that codebase. Different tool.

Use it as a diagnostic, never as a gate. A local pass is not evidence you will
clear the gate, and a local failure is not a reason to change your package. If
you keep a wrapper script for this, put the calibration table in its header so
nobody mistakes it for a pre-flight check.

## 6. Escape hatches, and when to reach for them

● **FACT.** The analyser reads these environment variables, among others:
  `DS_ENABLE_MANIFEST_FALLBACK`, `DS_MAX_DEPTH`, `DS_EXCLUDED_PATHS`,
  `DS_PIP_MANIFEST_FILE_NAME_PATTERN`,
  `DS_PIPCOMPILE_LOCKFILE_FILE_NAME_PATTERN`, `DS_ENABLE_VULNERABILITY_SCAN`,
  `SECURE_LOG_LEVEL`.

`DS_ENABLE_MANIFEST_FALLBACK` is the interesting one: manifest fallback is
disabled by default, and enabling it lets the analyser proceed from a plain
manifest when it cannot use a lockfile.

Two cautions. First, setting any of these requires editing the pipeline file in
the deployment repository, which is usually not something an application team
can do. Second, `DS_EXCLUDED_PATHS` and `DS_ENABLE_VULNERABILITY_SCAN` can make
a gate pass by scanning less, which is not the same as being secure. Reach for
them only with the security owner's agreement, and record why.

## 7. Fact, inference and unknown, in one place

**Established as fact:**
● The failure presents with no error text, no SBOM, and a misleading label.
● `pyproject.toml` is the only root-file difference between two passers and one
  failure.
● Header form, hash-locking and multiple `.in`/`.txt` pairs do not decide the
  outcome.
● A locally built open-source analyser disagrees with the platform on two of
  three known samples.

**Inference, acted on but not proven:**
● That adding `pyproject.toml` is what clears the gate. Two positive controls,
  one negative control, and a mechanism visible in the analyser's source. This
  is the best-supported change available, and it is still an inference until a
  green pipeline confirms it.

**Unknown:**
● The analyser's actual error message. Nobody has seen it. Until someone does,
  every explanation of this failure, including this document's, is reasoning
  from the outside.

**If you are the person who finally sees that error text, add it here.** That
single paragraph would be worth more than the rest of this document.

## 8. Provenance

Assembled from: the Legion pipeline job logs of 26 and 27 August 2026; the
package roots of PSIRENS 1.5.3 and Enlightenment 0.23.3, both confirmed by
their owner as having cleared the gate; and the source of GitLab's
open-source `dependency-scanning` analyser, cloned and built to read its
package-manager registration tables and to calibrate its predictive value.

A prior document, `DEPENDENCYSCANNING.md`, attributed this failure to a
`requirements.txt` whose pip-compile header was not on line 2. That diagnosis
was correct for the codebase it was written about. It does not transfer, and
PSIRENS disproves it as a general rule. Treat inherited diagnoses as
hypotheses to test against your own package, not as answers.
