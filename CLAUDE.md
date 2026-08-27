# CLAUDE.md — UDL Tactics App (`legion`)

Read this first, every session. It is the entry point; `HANDOFF.md` has the
full history if you need it, `READINESS.md` has the current gap analysis,
`CHANGELOG.md` has the version-by-version detail.

## What this is

A FastAPI service that lets Bluestaq analysts track, edit, and archive
Russian and Chinese ASAT/RPO satellite systems over time, cross-checking
entries against live UDL data. Server archetype, Python, deployed as a
container to the Bluestaq App Store.

Current version: see `src/VERSION` (single source of truth — everything
else, the FastAPI app metadata, the `/version` endpoint, reads from it).

## The two-repository model — read this before touching git or CI

This is the single most important thing to not lose in the move:

- **This repo (GitHub)** is where development happens now: code, tests,
  version bumps, `git log`.
- **A separate GitLab repo**, `vanguard-engineering/app-store-apps/legion`
  on Bluestaq's internal instance, is the actual App Store deployment
  target. It is not reachable from a normal internet connection or a
  public GitHub Actions runner — it lives on Bluestaq's own infrastructure.
- **Critically: uploading a new version zip to the App Store does NOT
  update `.gitlab-ci.yml` in that GitLab repo.** That file is only editable
  by a direct commit to the GitLab repo itself. This cost three failed
  pipeline uploads to discover — see `HANDOFF.md` for the full story. A
  copy of the corrected `.gitlab-ci.yml` lives in this repo for reference
  and version-control history, but **do not assume changing it here
  propagates anywhere** — it doesn't, until someone with GitLab access
  commits the same change there directly.

Practical implication: when the App Store submission process changes
(paths, stages, scan config), that change has to land in two places by two
different mechanisms — a code/zip change here, and a direct GitLab commit
there — and they will drift if only one happens.

## Current blocker (as of this handoff)

The GitLab pipeline has **never once run a stage successfully** across
three upload attempts. Root cause, fully diagnosed: `.gitlab-ci.yml` in the
GitLab repo still references a `udl-tactics-app/` subdirectory that hasn't
existed since the very first (accidentally nested) upload. Three lines are
wrong (the Anchore `dockerfile:` input, the SonarQube `base-dir:` input,
and the `podman build -f` line in `podman-build`). The fix has been handed
to **Koen** (engineering lead for that repo) via Teams, asking him to either
make the edit directly or grant write access. **Status: pending, as of this
handoff.** Check with Ash/Koen before assuming this is resolved.

Do not re-attempt "fix the zip" for this — it's proven not to work. The fix
has to be a direct commit to the GitLab repo's `.gitlab-ci.yml`.

## What's verified vs. not

Genuinely verified (re-run and confirmed, not just written):
- 79 tests passing, 1 correctly skipped (see below), coverage ~96%.
- `pip-audit` clean, `ruff`/`mypy`/`bandit` clean.
- Both `requirements.txt` (hash-locked, includes test tooling — this is
  what the platform's TEST stage installs) and `requirements-runtime.txt`
  (hash-locked, lean, no test tooling — this is what the Dockerfile
  installs) verified by installing each into a genuinely fresh venv and
  running the real test/app-build sequence against it.
- Live smoke-tested as a real running process (not just TestClient): auth
  gating, anti-shrink PATCH, archive-not-delete, persistence across a
  restart.

**Container build: now verified (20 August 2026).** It builds, it runs, it
serves. Zero setuid/setgid entries in the final image, no base-image layer
history survives the scratch stage, injected `PORT` honoured, 49 seeded
records served, token-gated writes and persistence across a restart all
confirmed live. One correction: the final stage produces two layers, not
one, because the trailing `WORKDIR /app` adds a metadata layer after the
flatten. The scan property still holds. Full method, the single sandbox-only
deviation, and what remains untested are in `READINESS.md`.

That build turned up two runtime findings. Both are now closed:
● **The audit line never reached the log. Fixed in 0.4.2.** Nothing
  configured logging, so `udl_tactics_app.audit` had no handler and sat at
  WARNING, and every `audit_logger.info(...)` was discarded: the audit trail
  had been absent for the life of the project. `configure_logging()` in
  `src/app.py`, called from `build_app()`, attaches one stdout handler to the
  parent logger, with an audit-aware formatter so audit records emit as the
  bare JSON line they already are, and the audit logger pinned to INFO so
  `LOG_LEVEL` cannot silence a compliance record. Verified in the running
  container, not asserted. Do not add a second handler to the audit logger
  itself, and do not turn propagation off: the first duplicates every line,
  the second breaks `caplog`. Both are explained in the function's docstring.
● **`STORAGE_MOUNT_PATH` and the `/app/data` fallback: by design.** Ash
  confirmed on 20 August 2026 that the file-storage add-on will always be
  present, so the unwritable `/app/data` fallback is not reachable in
  deployment. No code change. Settled, do not relitigate.

A note on why the audit gap survived so long, worth carrying into anything
new: the tests that covered it asserted through `caplog`, which installs its
own root handler. The trail appeared to work under test and only under test.
If a test proves an observability behaviour, assert on what a real handler
writes.

**Pipeline status, 27 August 2026.** Container Build now **passes**: the
stale `udl-tactics-app/` path that blocked every upload since the beginning
is gone. Secret Detection, Dependencies, SAST, Test and Dockerfile Lint all
pass. Code Quality was **skipped**, not passed, so the 31 SonarQube fixes in
0.4.3 are still unconfirmed by the platform. **Dependency Scanning is the one
red gate**, and it fails with no error text: the analyser exits 1 after about
eight seconds having written no SBOM, and the platform relabels any non-zero
exit as "Vulnerable dependencies found". No package is actually flagged. See
`READINESS.md` for the full investigation, including a local run of the
analyser against the real package that exits 0 with a valid 57-component
SBOM, and for why that result is strong but not conclusive. Use
`scripts/verify-dependency-scan.sh` before the next upload.

**Still not verified:**
● The GitLab pipeline itself, per the blocker above.
● The `prep` stage's OS patch layer. `apt-get update` was blocked by the
  build environment's egress policy and the `|| true` swallowed it, so the
  upgrade applied nothing in that build.

## Architecture, briefly

- `src/app.py` — app factory (`build_app`), CORS, two-tier rate limiting.
- `src/udl_client.py` — talks to UDL's `/udl/notification` (JCO HRR feed)
  and `/udl/elset` endpoints. These paths and field names are copied from
  CONTEXT-001's verified LEARNED register (a separate Claude.ai project's
  context file Ash maintains) — treat them as fact, not guesses, **except**
  two things explicitly flagged INFERENCE in that file's docstrings: (1)
  whether `/udl/elset` accepts a direct `satNo=` filter, (2) the
  notification `window_hours` semantics (full baseline vs. deltas only).
  Confirm both against a live UDL session before trusting them further.
- `src/store.py` — atomic JSON store for the tracked-systems catalogue
  (not a database — deliberate, per Bluestaq's data-layer standard for
  low-concurrency, non-relational state). Anti-shrink merges, archive not
  delete, backed up before every archive, schema-versioned.
- `src/routes/systems.py` — CRUD API. Reads public, writes gated by a
  shared bearer token (`TEAM_TOKEN`).
- `src/static/index.html` — the admin UI served at `GET /`. Single file,
  vanilla JS, fetches the API directly.
- `src/seed_data.py` — the 49 systems from `Red_ASAT_Systems.xlsx`,
  mirrored verbatim from `tactics_wiki.html`'s data — do not re-derive
  these values from anywhere else; this is the canonical source.
- Credentials: env vars first (`UDL_USERNAME`/`UDL_PASSWORD`), falling back
  to `~/.config/phase_offset/credentials.ini` `[udl]` for local dev only —
  never present inside the built container.

## Working in this repo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # includes test tooling, hash-locked
cp .env.example .env
pytest --cov=src --cov-report=term-missing
python -m src.main                        # :8080, UI at http://localhost:8080/
```

Bumping the version (updates `src/VERSION`, prepends a `CHANGELOG.md`
entry, commits, tags — one command, don't do these by hand separately):

```bash
./scripts/bump_version.sh 0.5.0 "what changed, in one line"
```

## Standing instructions

- UK English, no em-dashes, lead with the point (Bluestaq house style).
- Fact/inference/speculation discipline: never assert something as fact
  that hasn't been verified against a live system. Mark an inference
  explicitly (this file and `src/udl_client.py` do this already — keep it
  up if you add new UDL behaviour).
- Before claiming something works: run it. This project has a documented
  history (see `HANDOFF.md`) of failures caused by asserting instead of
  testing — a stale `.gitlab-ci.yml` fix that silently never applied, a
  `requirements.txt`/`requirements-runtime.txt` split built backwards from
  the actual platform contract. Both cost a full upload cycle to catch.
  Verify against the real command, the real file, the real fresh install —
  not the working directory's cached state.
