# READINESS.md — UDL Tactics App (`legion`)

**Generated:** 20 August 2026
**Version at time of report:** 0.3.3 (`src/VERSION`)
**Scope:** pre-flight estimate per `app-store-readiness`. Not the platform's binding decision.

## Band: Not yet

One blocker, and it is not something local work can close: **the GitLab pipeline has never once run a stage successfully.** Every dimension below that *can* be verified locally now passes; the ones that require the actual platform runner remain unconfirmed until the `.gitlab-ci.yml` path fix (flagged to Koen, three lines: `dockerfile:`, `base-dir:`, and the `podman build -f` line, all still pointing at a `udl-tactics-app/` subdirectory that no longer exists) lands on `main` and a version upload actually clears Secret Detection.

**Score:** 14 of 16 applicable dimensions pass locally. The band is capped at "Not yet" regardless of that score, because a red/never-run required pipeline is a blocker by the skill's own rule — this report does not soften that.

## Per-dimension table

| # | Dimension | Result | Weight | Note |
|---|---|---|---|---|
| 1 | Verification loop green | **Pass** | blocker | 79 passed, 1 skipped (documented below), 0 failed, fresh venv |
| 2 | Coverage ≥ 80% | **Pass** | heavy | 95.9% |
| 3 | No secret in source/history | **Pass** | blocker | Grepped for credential-shaped strings; `.env.example` placeholder-only; fresh git history, one commit chain |
| 4 | Server contract: PORT/0.0.0.0/health/non-root/no ENV PORT | **Pass** | blocker | Confirmed live (smoke-tested as a running process, not just TestClient) |
| 5 | Container package flat at root | **Pass** | blocker | Verified in the actual zip: `Dockerfile`, `.gitlab-ci.yml`, requirements files all at root |
| 6 | Runtime hardened AND flattened (no setuid/setgid in layer history) | **Fixed, build unverified** | blocker | Restructured to a `FROM scratch` + single `COPY --from=prep / /` final stage. Cannot build-test - no Docker daemon in this environment. Needs a real `docker build`/`podman build` before trusting this fully |
| 7 | Coverage report at the gate's exact path | **Pass** | heavy | `coverage.xml` at root, matches `sonar-project.properties` and `.gitlab-ci.yml`'s `SONAR_SCANNER_OPTS` |
| 8 | Reproducible install, committed lockfile, no unaddressed CVE | **Pass** | heavy | Hash-locked via `pip-compile --generate-hashes`; verified clean install + full test run from a genuinely fresh venv on both `requirements.txt` and `requirements-runtime.txt`; `pip-audit` clean |
| 9 | Container: upload is a testable source tree, pipeline simulation green, emits coverage | **Likely** | blocker (container) | Simulated the platform's exact `pip install -r requirements.txt` + `pytest --cov --cov-report=xml:coverage.xml` sequence from a clean venv against the real package contents. Never run through the actual GitLab runner/podman - that's the pending blocker |
| 10 | Per-commit static analysis keeps violations at zero | **Likely** | heavy | `ruff check`, `ruff format --check`, `mypy --ignore-missing-imports`, `bandit` all clean. Not the exact SonarQube ruleset (no `sonar-scanner` access from this environment - CONTEXT-001 already documents this as a standing gap); this is the closest local approximation |
| 11 | Negative assertions classified per environment | **Pass** | blocker | One test (`readyz` 503-on-unwritable-storage) only holds under a non-root runner; explicitly `skipif(os.geteuid() == 0, ...)` with a reason, not silently deleted or left falsely passing |
| 12 | CI mirrors local loop, latest run green | **Fail (blocker)** | blocker | Zero of three upload attempts have cleared even Secret Detection. Root cause identified (stale `udl-tactics-app/` paths in `.gitlab-ci.yml`, confirmed byte-for-byte against two separate pastes of the file); fix handed to Koen, not yet landed |
| 13 | Version stamp + structured audit line, no secret in logs | **Pass** | medium | `src/VERSION` read at import time, `/version` endpoint; `create`/`update`/`archive` each emit one sanitised, length-capped JSON audit line |
| 14 | Accessibility to WCAG AA | **Pass** | medium | Fixed: label/`for` associations on every form control (were unassociated), `<main>` landmark, skip link, `aria-live` on the status message, `role="status"` on filter-result count. Computed contrast ratios for every text/background pair in use — one real failure found and fixed (`--text-faint` was 2.81:1, now 4.61:1). Structural/computed checks only; no live screen-reader pass run |
| 15 | Surgical structure, no dead code | **Pass** | medium | `ruff` clean, one unused import removed, one blind `except Exception` (masking real errors as 429s) fixed to catch the specific exception |
| 16 | House voice in user-facing copy | **N/A** | light | Internal analyst tool, not customer-facing copy |

## Blockers (must clear before "Ready")

1. **The GitLab pipeline has never run successfully.** Owner: `ci-cd`, `appstore-gate-compliance`. Fix: land the three-line `.gitlab-ci.yml` correction (already handed to Koen) and get one clean upload through Secret Detection onward. Nothing else in this report can substitute for a real green run.
2. **Container flattening is unverified.** Owner: `packaging`, `app-store-deployment`, `deploy-recipes`. Fix: `docker build .` (or `podman build`) needs to actually succeed against the new three-stage Dockerfile before relying on it - this environment has no Docker daemon to prove that locally.

## What would raise the band

- Blocker 1 clearing (a real green pipeline run) moves this to **Likely after fixes**.
- Blocker 2 confirmed (a successful local or CI container build off the flattened Dockerfile) closes the second gap.
- Once both clear, re-run this check: if dimensions 9 and 10 are confirmed against the real runner (not just simulated), the band moves to **Ready**.

## Skills consulted for this pass

`app-store-readiness` (this report), `toolchain-adapters` (Python command mapping), `dependencies` (lockfile standard), `testing-standards` (environment-scoped assertions), `observability-and-audit` (audit line, readiness probe), `accessibility` (audit checklist, contrast computation), `security-hardening`, `app-store-deployment`, `deploy-recipes`, `code-architecture`, `packaging`, `data-layer`, `api-and-integration`.

Not consulted, and worth a look if anything above regresses: `ci-cd` (pipeline structure itself, beyond the path fix), `release-and-deploy` (the deploy-gate step once a build actually succeeds), `environment-setup` (if this needs to run on a fresh machine from scratch).

## Honesty note

This report was generated retroactively, after three failed upload attempts, not from scaffold time. That is itself the finding worth remembering: several of the fixes above (the audit line, the readiness probe, the hash-locked lockfile, the accessibility pass) are exactly the kind of thing `app-store-readiness` is built to catch *before* a first submission, cheaply, rather than reactively after a review finds them. Next project on this baseline: run this skill at scaffold time, not after the third failed pipeline.
