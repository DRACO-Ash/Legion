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

## Status: shipped

**Legion 0.4.6 passed all ten App Store stages and deployed on 28 August 2026.**
Secret Detection, Dependencies, SAST, Dependency Scanning, Test, Code Quality,
Dockerfile Lint, Container Build, Container Scan and Deploy are all green. The
application is Active.

The two-repository model above still governs everything, and the stale
`udl-tactics-app/` paths in the GitLab `.gitlab-ci.yml` were fixed directly in
that repository, not by any change here. That remains the standing lesson: a
change to the pipeline lands in two places by two different mechanisms.

**What actually cleared Dependency Scanning**, after six upload cycles: the
lock files were regenerated with `uv pip compile --generate-hashes
--no-annotate`. The pip-compile `# via` annotations were the cause. No package
version moved. A root `pyproject.toml` with a `[project]` table was necessary
but not sufficient, proven by 0.4.5 failing with one present. Full account,
including the two theories that died on contact, is in
`docs/APP-STORE-DEPENDENCY-SCANNING.md`.

Regenerate lock files only with `--no-annotate`. Note that the
`appstore-python-gate` skill's own `scripts/lock.sh` omits that flag.

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
`scripts/verify-dependency-scan.sh` only as a diagnostic: calibrated against
three packages with known outcomes it was wrong on two, so it does not predict
the gate and its header says so.

**The `pyproject.toml` at the root is load-bearing, do not delete it.** It was
added in 0.4.4 because it is the only root file present in both App Store
applications known to clear Dependency Scanning (PSIRENS 1.5.3 and
Enlightenment 0.23.3) and absent from Legion. It carries `[project]` metadata
and deliberately no dependency list, matching their shape. `bump_version.sh`
keeps its version in step with `src/VERSION`; do not edit that line by hand.

**Still not verified:**
● The GitLab pipeline itself, per the blocker above.
● The `prep` stage's OS patch layer. `apt-get update` was blocked by the
  build environment's egress policy and the `|| true` swallowed it, so the
  upgrade applied nothing in that build.

## The Code Quality gate has four conditions, not one

Learned the hard way across 0.4.7 and 0.4.8. The SonarQube gate fails on any
of these, and only the first produces anything resembling an error message:

● New issues = 0. The local mirror in `tests/test_sonar_contracts.py` covers
  the rules that have actually fired, including "Use logging.exception()
  instead", which fires on `logger.error` inside an `except` block and cost
  three upload cycles on its own because the gate's only visible message is
  "Quality Gate FAILED". It must scan `tests/` as well as `src/`,
  because `sonar-project.properties` sets `sonar.tests=tests`.
● Coverage on new code. Measure the changed lines, not the project total: a
  95% project can still ship a poorly covered diff.
● **Duplicated lines on new code.** This one has no local check and is easy to
  trip: a new test file that copies an 11-line fixture from an existing one is
  duplicated enough to fail on its own. Shared fixtures live in
  `tests/conftest.py` (`make_seed_record`) for exactly this reason.
● Security hotspots reviewed. If this is the failing condition, no upload will
  ever fix it: a human must review them in the SonarQube user interface.

The failed job uploads `sonar-quality-gate.json`, which names which condition
failed, plus `sonar-issues.json` and `sonar-hotspots.json`. Read those first.
The job log itself says only "Quality Gate FAILED".

**The gate also reads `src/static/index.html` as CSS, JavaScript and HTML**,
not just the Python. Rules that have fired there: nested ternaries, nested
template literals, `getAttribute("data-...")` over `.dataset`, an unawaited
async call at module top level, a duplicate CSS selector, and a constant array
used for membership tests instead of a `Set`. Every one of those now has a
local mirror, calibrated against the upload that reported it:
`tests/test_sonar_contracts.py` for the CSS and JavaScript rules, and
`tests/test_sonar_cognitive_complexity.py` for python:S3776, which reproduced
the platform's 25 and 18 exactly. Run `pytest` before packaging and the gate
has nothing left to find.

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
- `src/orbits.py` — the orbital derivations behind the charts: epoch
  parsing, Julian date, GMST (IAU 1982), GEO mean longitude, drift rate,
  and the regime-to-metric rule. Pure functions, stdlib only.
- `src/family_elements.py` — assembles one family's element sets into
  chart-ready series. Owns the fan-out to UDL, the per-satellite failure
  handling and the colour assignment.
- `src/cache.py` — a small in-process TTL cache so a family chart does not
  re-ask UDL for element sets it fetched seconds ago.
- `src/static/index.html` — the admin UI served at `GET /`. Single file,
  vanilla JS, fetches the API directly.
- `src/seed_data.py` — the 49 systems from `Red_ASAT_Systems.xlsx`,
  mirrored verbatim from `tactics_wiki.html`'s data — do not re-derive
  these values from anywhere else; this is the canonical source.
- Credentials: env vars first (`UDL_USERNAME`/`UDL_PASSWORD`), falling back
  to `~/.config/phase_offset/credentials.ini` `[udl]` for local dev only —
  never present inside the built container.

## The family movement charts: rules that must hold

Added in 0.5.0, tightened in 0.6.0. Five things are load-bearing and easy to
undo by accident:

● **Only JCO HRR rank 0 to 3 is ever pulled.** Ash's rule, 6 September 2026:
  rank 4 and 5 entries are not trustworthy enough to plot, and a wrong line is
  worse than a missing one. An object absent from the feed carries no rank and
  is not pulled either. One feed call ranks a whole family, and the exclusions
  are named under the chart. If the feed call fails, the whole request fails:
  a gate that cannot be applied must stop the pull, never quietly open. Do not
  "improve" this by falling back to pulling everything when the feed is down.
● **Mean longitude is an approximation, and the UI says so.** UDL has no
  longitude field; it is derived as `RAAN + argOfPerigee + meanAnomaly -
  GMST(epoch)`, which holds for a near-circular, near-equatorial orbit. It is
  good for drift and station-keeping, not for conjunction assessment. Do not
  quietly promote it to fact anywhere.
● **`/udl/elset/history` is INFERENCE, not FACT.** CONTEXT-001's LEARNED
  register documents neither the path nor a `satNo`/`epoch` filter on it; it
  is a pattern-match against UDL's general `/history` convention. The client
  therefore treats a 4xx as "not available here" and falls back to the latest
  element set, while a 5xx or a timeout still raises. Confirm the endpoint
  against a live pull before trusting a chart's history depth.
● **One metric, one axis, always.** GEO objects are charted on mean
  longitude, everything else on mean motion, and the two never share a plot.
  A dual-axis chart invents a correlation that is not in the data. A family
  holding both gets two charts.
● **Colour follows the satellite, never its position in the result.** The
  server sends a `colour_index` fixed by the family's launch-order member
  list, so filtering never repaints a surviving line. The palette is the
  validated eight-slot dark set, held once in CSS custom properties and read
  from there by the chart code; the order is the colour-vision-deficiency
  safety mechanism. Never reorder it, and never add a ninth: a family past
  eight lists the remainder as "not charted". If the palette ever changes,
  re-run the dataviz skill's `validate_palette.js` against the panel surface
  (`#152238`) first.

● **The three token outcomes stay distinguishable.** No token configured on
  the deployment is 503 with a reason; a wrong or missing bearer token is 401;
  a match passes. The UI turns the 401 into different advice depending on
  whether it sent a token at all, and compares the length it holds against the
  `team_token_len` that `/readyz` publishes. Do not collapse the two 401
  causes back into one message: "set the team token" is useless advice to
  someone who has just set one, and it cost a round of live debugging to find
  that out. Lengths only, never the value.

`tests/test_ui_contracts.py` pins the parts of this that are checkable from
Python, including that every path the UI fetches exists in the app's OpenAPI
schema, and that catalogue values are escaped before reaching the markup.

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
