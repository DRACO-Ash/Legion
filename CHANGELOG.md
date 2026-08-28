# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/). Pre-1.0: minor bumps may include
breaking changes, since nothing has shipped to the App Store yet.

## [0.4.9] - 2026-08-28

Remove duplicated lines on new code, take new-code coverage to 100%, and correct the stale SonarQube project key.


## [0.4.8] - 2026-08-28

Clear the SonarQube issues introduced by the 0.4.7 fix, and widen the local S1192 mirror to the tests tree, which is where it missed one.


## [0.4.7] - 2026-08-28

Survive a filesystem without rename, make readiness exercise the real read path, and fail closed on writes when no team token is configured.


## [0.4.6] - 2026-08-27

Regenerate lockfiles with uv --no-annotate, matching the generation method of a package known to clear Dependency Scanning. Package set, versions and hashes unchanged.


## [0.4.5] - 2026-08-27

Adopt the appstore-python-gate skill: exclude .gitlab-ci.yml and tooling from the upload package, and make the fail-open OS patch step record its outcome.


## [0.4.4] - 2026-08-27

Add pyproject.toml to pair with requirements.txt for GitLab Dependency Scanning, matching the shape of two App Store applications known to clear that gate.


## [0.4.3] - 2026-08-26

Clear all 31 SonarQube quality-gate issues: duplicated literals named as constants (data proven unchanged), status roles expressed as <output>, and the local-dev entrypoint no longer binds all interfaces.


## [0.4.2] - 2026-08-20

Fix the audit trail never reaching the log: configure_logging() attaches a stdout handler in build_app, audit lines emit as bare JSON and are never silenced by LOG_LEVEL.


## [0.4.1] - 2026-08-20

Add CLAUDE.md and HANDOFF.md ahead of moving primary development to Claude Code / GitHub. No code changes.


## [0.4.0] - 2026-08-20

app-store-readiness run properly for the first time: hash-locked dependencies, flattened container (unverified build - no Docker daemon available), structured audit logging, real storage-writability probe, accessibility fixes (label associations, contrast, landmark, live region), lint/type-check clean. READINESS.md added: band is Not yet, blocked on the pending .gitlab-ci.yml path fix and an unverified container build - not something local work can close alone.


## [0.3.3] - 2026-08-20

Pre-flight against the App Store's documented pipeline checklist: confirmed no binaries/build output/pycache committed, confirmed Dockerfile at root, confirmed coverage.xml lands at the exact expected path, confirmed pip-audit clean. Suppressed one bandit finding (B104, 0.0.0.0 bind on the local-dev entrypoint) with an inline justification - required by the platform's own PORT contract on the real gunicorn entrypoint, not a real vulnerability.


## [0.3.2] - 2026-08-20

Add .gitlab-ci.yml with corrected build/scan paths (dockerfile, base-dir, podman build context) - the CI file baked into the repo at onboarding still referenced the stale udl-tactics-app/ subdirectory from the original nested-zip upload.


## [0.3.1] - 2026-08-19

### Fixed
- `requirements.txt` and `requirements-runtime.txt` had the App Store test/
  runtime contract backwards - the platform's TEST stage only ever runs
  `pip install -r requirements.txt` then `pytest`, so test tooling
  (pytest, pytest-cov, respx, pip-audit) has to live in `requirements.txt`,
  not the other file. Swapped; `requirements-runtime.txt` is now the lean,
  test-tooling-free file the Dockerfile installs into the image. Verified
  by installing each file into a clean venv and running the platform's
  exact TEST-stage command.
- Bumped pytest 8.3.3 → 9.0.3 and pytest-cov 5.0.0 → 7.1.0 (CVE on the old
  pytest pin).

## [0.3.0] - 2026-08-14

### Added
- Persistent tracked-systems catalogue: atomic JSON store (`src/store.py`)
  on the App Store file-storage add-on, schema-versioned, forward-migrating,
  backed up (pruned to the last 10) before every archive.
- Seed data: the 49 systems from `Red_ASAT_Systems.xlsx`, mirrored verbatim
  from `tactics_wiki.html`'s DATA array into `src/seed_data.py`.
- CRUD API (`/api/systems`, `/api/systems/{id}`): list/filter is public;
  create/update/archive gated by the team token. Updates are anti-shrink
  merges. Archive, not delete - a retired record stays auditable.
- Admin UI (`GET /`, `src/static/index.html`): browse, filter, add, edit,
  archive systems from the browser, with a session-scoped team-token field
  for write access.

## [0.2.0] - 2026-08-14

### Changed
- Rewrote the UDL client against CONTEXT-001's verified LEARNED register
  instead of an invented `/udl/onorbit` endpoint: `/udl/notification`
  (the JCO HRR high-interest feed PSIRENS already pulls) for search/lookup,
  and `/udl/elset` for orbital elements.
- Added `GET /api/udl/clash-check`: resolves the COSMOS-2612/2613/2614
  NORAD 68762 collision flagged in the Tactics Wiki against live UDL data.

## [0.1.0] - 2026-08-14

### Added
- Initial FastAPI service scaffold: app factory, config (env vars first,
  `~/.config/phase_offset/credentials.ini` fallback for local dev), two-tier
  rate limiting, constant-time bearer token auth, CORS with fail-closed
  wildcard-origin guard.
- Health/readiness endpoints (`/healthz`, `/readyz`).
- Hardened multi-stage Dockerfile (non-root uid 10001, correctly ordered
  setuid/setgid sweep, platform `PORT` contract).
- Full test suite from day one (pytest, respx for HTTP mocking, coverage
  gate).
