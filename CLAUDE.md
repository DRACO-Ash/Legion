# CLAUDE.md: UDL Tactics App (`legion`)

Standing rules, read every session. Each rule is short here and its full
account (what failed, how it was found, how the fix was proved) is in
`docs/PROJECT-RECORD.md` under the heading given in brackets. Read that
section before changing anything a rule protects. `READINESS.md` is the gap
analysis, `CHANGELOG.md` the per-version detail, `HANDOFF.md` the early
history, `docs/SONAR-RULE-REGISTER.md` every rule the Code Quality gate has
fired.

## What this is

A FastAPI service for Bluestaq analysts to track, edit and archive Russian
and Chinese ASAT and RPO satellite systems, cross-checked against live UDL
data. Python, deployed as a container to the Bluestaq App Store. The version
lives in `src/VERSION` only; everything else reads it.

## Status

0.19.3 is deployed and healthy (26 November 2026, read from the platform):
every stage passed, Logging and Container Scan included, and the deployed
`/readyz` reports `os_patch_status` "patched". Still open:

● The GitLab pipeline file itself is not visible from here (two-repository
  model, below).
● The notification feed's `window_hours` semantics (full baseline or deltas)
  is INFERENCE. `scripts/udl_live_check.py` settles it where UDL is reachable.
● `/udl/elset/history` is INFERENCE; the diagnostics report its real status.
● A bulk element-set pull is possible (`epoch` alone works) and not built,
  because the response size has not been measured. Measure first.
● [DECISION - Ash] item 5: the relative-motion view against a counterpart
  outside the catalogue needs a confirmed UDL path for a target's element
  sets. SJ-25/SJ-21 is buildable now; COSMOS-2576/USA-314 is not.

## How to work here

● **UK English, no em dashes or double dashes, `●` bullets, lead with the
  point.**
● **FACT, INFERENCE, SPECULATION.** Never assert as fact what was not
  verified against a live system, and mark inferences in code and docs.
● **Done means proven.** Run the real command, the real fresh install, the
  real browser. Quote the command beside any count. Every message this UI
  shows about scope was wrong at least once and each was caught by driving
  the page, never by reading code.
● **Calibrate every guard by sabotage before believing it.** Put the defect
  back, confirm a named test fails, restore. A guard that passes because it
  never looked is the most repeated mistake in this project: tests reading a
  `response_model` that strips the field, an error body, a guessed shape, a
  file compared with itself, `caplog` instead of a real handler.
● **State the exit criterion at the start of gate or release work**, and
  check in with Ash after three gate rounds either way.
● **Prove a cause before automating around it.** Two identical failures end
  a retry loop. A two-week tag-push retry ran on an unproven cause.
● **Tags cannot be pushed from a cloud session**: the Claude Code proxy
  answers 403, and the repository has no tag rulesets. Create the tag, then
  hand Ash the commit, tag name and push command.
● **Report blockers in three lines**: what Claude can fix now, what Ash must
  do (exact steps), what cannot be done here and the workaround.
● **Before applying a mechanical fix across the codebase, ask what property
  the old shape provided by accident** (`async def` was serialising the
  store's writes).

## The two-repository model

Development happens in this GitHub repository. The App Store deploys from a
separate GitLab repository, `vanguard-engineering/app-store-apps/legion`, on
Bluestaq's internal instance. **A version upload does not update that
repository's `.gitlab-ci.yml`**; only a direct commit there does. The copy
here is reference only. A pipeline change lands in two places by two
mechanisms or it drifts. [The two-repository model]

## Releasing

```bash
./scripts/check-quality-gate.sh                 # every local check, about 30 s
./scripts/bump_version.sh 0.x.y "one line"     # VERSION, CHANGELOG, commit, tag
./scripts/package.sh                            # builds from the tag, tests the archive
```

● Never pipe these through `tail`: a missed warning once cost a full upload.
● `package.sh` builds from the tag, extracts the archive and runs the suite
  inside it, and writes `<zip>.sha256`. Send Ash the zip, its size and its
  SHA-256. Ash uploads and submits; Claude never does.
● **A release must change a Python file under `src/`**, or
  `code-quality-verify` fails with nothing to measure. Both scripts refuse;
  `--allow-unmeasurable` makes shipping one a decision.
● **Regenerate lock files only with `uv pip compile --generate-hashes
  --no-annotate`.** The `# via` annotations broke Dependency Scanning for six
  uploads. Never edit a lock file by hand. The root `pyproject.toml` is
  load-bearing and carries no dependency list; `bump_version.sh` keeps its
  version. [Status: shipped]

## The Code Quality gate has five conditions, not one

New issues zero; coverage on new code; **duplicated lines on new code** (no
local check: shared fixtures live in `tests/conftest.py`); security hotspots
reviewed (a person does that in SonarQube); and coverage measurable at all.
[The Code Quality gate has five conditions, not one]

● **The analysis reads every file in the archive**: `src/`, `tests/`,
  `scripts/`, `src/static/index.html` as HTML, CSS and JavaScript, and the
  Dockerfile, whatever `sonar-project.properties` says.
● **Read `docs/SONAR-RULE-REGISTER.md` before writing code.** A rule goes in
  when the platform reports it, is calibrated against that upload, and never
  comes out. The mirrors are `tests/test_sonar_*.py`.
● **Parse the structure, never the line.** Line-based mirrors missed a
  three-line nesting and a CSS property on a continuation line.
● **Leave the coverage configuration alone.** `relative_files = True` makes
  the report's paths point at files that do not exist.
● **Shapes this codebase keeps generating**: literal route paths, never
  concatenated; `Annotated` parameters, not `Query(...)` defaults; a label
  on every input; native `<dialog>` and `<fieldset>`, never `role="dialog"`
  or `role="group"`; no `tabindex` or list roles on non-interactive
  elements; `.some()` not `.find()` as a test; `logging.exception` in an
  `except`; one call per `pytest.raises`; `dict.fromkeys`.
● **Route handlers are plain `def`**, and `_serialised` in `src/store.py`
  wraps every writer. Without it twelve concurrent edits lost ten.

## The container image

[The container image: three rules that are easy to undo]

● **Both `FROM` lines pin the same digest, digest alone**, tag in a comment.
  Refresh both together, rebuild, re-verify.
● **pip, setuptools and wheel are deleted from the runtime image** and the
  build fails if any survive. Never fix an installer advisory by upgrading
  pip.
● **A base image move must not move a package version.** Prove the existing
  hashes cover the new interpreter under `--require-hashes` first.
● **Packages nothing loads are purged, fail-closed** (Ash, 20 November
  2026). `NEEDED` in `tests/test_dockerfile.py` lists what must never go;
  trace loaded libraries again before adding to the purge.
● **The patch status must not lie**: `apt-get update --error-on=any`, served
  as `os_patch_status` in `/readyz`.
● **An Anchore policy fails only on a `STOP` row.** Find it before changing
  a version; the advice text names packages whatever the real cause.

## Logging: the platform standard

`src/logging_standard.py` owns the format, `src/gunicorn_conf.py` routes the
server's own loggers through it, and `tests/test_logging_config.py` ends by
running real gunicorn. [0.19.1: what the 0.19.0 upload found] and
[Status: shipped]

● One JSON object per line on stdout. One handler, on the root logger, named
  `udl-tactics-app-stdout`; never a second, and none on the audit logger.
● gunicorn's error logger carries that handler with propagation off. **Never
  name anything `logconfig` in `src/gunicorn_conf.py`**: gunicorn reads it as
  a setting and stops starting.
● Root stays at WARNING (httpx logs query strings at INFO). The audit logger
  is pinned to INFO so `LOG_LEVEL` cannot silence a compliance record.
● `RequestLogMiddleware` is outermost and pure ASGI. Every line written
  during a request carries `url.path`, `http.request.method` and
  `user_agent.original` (empty when absent), plus the request id and user
  when sent. The request line adds the status and `event.outcome`. Never a
  query string.
● The ISO timestamp and the 400 failure threshold are INFERENCE.
● Assert on what a real handler writes, never through `caplog`.

## Decisions Ash has made: settled, do not relitigate

● **No authentication** (10 September 2026). Reads, writes and UDL lookups
  are open; the platform is the access control. `ALLOWED_ORIGIN` refuses `*`
  unconditionally, the strict rate limiter is the only control on the UDL
  budget, and tests fail if token machinery returns. Authentication, if ever
  needed, takes identity from the platform. [There is no authentication]
● **Unclassified, publicly available information only** (11 September).
  `src/classification.py` holds the marking in Ash's words and `/version`
  serves it; never invent a marking. An `internal_assessment` claim must
  cite its public basis. [Unclassified, publicly available information only]
● **Any DOK team member may sign off a family assessment** (14 September).
  A sign-off records an assertion, it does not authenticate one; the
  entitlement is stored beside the name; whitespace is refused.
  [Who may sign off]
● **Ranking is indicative and goes nowhere else** (14 September). Computed
  for display, never stored, never in a briefing or comparison, never a
  claim, inputs sourced. The guards read the store file on disk.
  [The application may rank, and only indicatively]
● **Only JCO HRR rank 0 to 3 is ever pulled** (6 September). If the feed
  fails, the request fails: a gate that cannot be applied stops the pull.
● **Relative mode anchors on the latest element set** (10 September).
● **The COSMOS-2612 to -2614 NORAD correction** (68762, 68763, 68764) is the
  one authorised change to the verbatim mirror (11 September), applied by a
  named migration, never by a rule. [The SATCAT snapshot]
● **The file-storage add-on is always present** (20 August); the
  `/app/data` fallback is unreachable by design.
● **The interface is the belt console** (Orbital Atlas merged), without the
  Bluestaq navy ground. [The belt console]

## The data: what must never be invented

● **`src/seed_data.py` is the 49 systems mirrored verbatim** from the
  spreadsheet. Never re-derive them. Seven candidates live apart in
  `src/candidate_systems.py`, each citing its source and naming its
  verifier; their catalogue numbers come only from the SATCAT snapshot and a
  test holds each against it. [Candidate systems] and [The SATCAT snapshot]
● **The SATCAT snapshot** (`reference/satcat_26195.dat`) is export-ignored;
  `scripts/extract_satcat.py` distils `src/satcat_extract.json`, which
  ships. `src/satcat_reconcile.py` checks the catalogue against it.
● **The claim is the atom.** A FACT needs a citation, a TBC needs a named
  owner, `asserted_by` is required, whitespace satisfies none of them, and
  an edit re-validates the whole merged claim. Observability is not
  confidence. A proximity mode names its counterpart. [The compendium layer]
● **Archive, never delete. A write that changes nothing is an error**, not
  a 200.
● **Migrations are keyed on a natural key**, idempotent by construction,
  never overwrite an edit, and skip what the store does not hold. The store
  is at `schema_version` 6. Prove a migration by breaking it on purpose:
  only calling the layer builder directly caught the second sabotage.
● **An epoch is never more precise on screen than in the source**; an
  instant has no end; a blank end reads "no end recorded", never
  "ongoing". [Phase 3]
● **Every graph edge comes from stored data and is sourced**, names the
  field it came from, and is dropped if it points nowhere. A solo
  behaviour is not a relationship. [Phase 4]
● **A seeded assessment loads unvalidated**, single-source claims at
  `moderate`, unknowns as TBC with an owner, speculation never promoted.
  [Phase 5]
● **A briefing carries every statement's marker, confidence and source**,
  in house style enforced by `tests/test_briefing.py`. An empty comparison
  cell says why. [Phase 6]

## UDL

[The elset call needs an epoch] and [The family movement charts]

● **`/udl/elset` needs an `epoch` bound** or answers 400; the default window
  is 168 hours and `get_elset` picks the newest epoch explicitly. Paths and
  field names come from CONTEXT-001's verified register.
● **Mean longitude is an approximation** (`RAAN + argOfPerigee + meanAnomaly
  - GMST`) and the interface says so.
● **A diagnostic never invents a value.** A successful probe reports no
  status; the history probe calls the path raw through `UDLClient.probe`.
● **UDL, CelesTrak and Space-Track are refused at this environment's
  proxy.** Credentials would not change that.

## The interface

`src/static/index.html`, single file, vanilla JavaScript. [The belt console],
[The family movement charts], [The dossier], [The theatre], [Triage]

● **The eight-slot series palette identifies a satellite.** Validated
  against `#0C121B`; never reorder it, never add a ninth, re-run
  `validate_palette.js` before any change. It is never used for provenance,
  graph nodes or chrome. Never colour alone: text carries every marker.
● **One metric, one axis; colour follows the satellite** (`colour_index`
  from launch order). Every message names the scope actually on screen.
● **Vocabulary is served, never copied into the markup**: the legend, the
  marking, the validation policy, the ranking label, category labels.
● **Triage spends nothing from the UDL budget**; charts pause while it runs.
● Traps: `const CSS` shadows `CSS.escape` (match on `dataset`); dialog
  overlay styling belongs on `[open]`; a name declared twice kills the whole
  module (a test catches it); markup the script binds to must come before it.

## Reading the platform directly: the App Store MCP server

`.claude/mcp/appstore-mcp.mjs` (0.14.2, reviewed before first run) is
registered by `.mcp.json`, and both are export-ignored. It reads pipeline
status, job logs, pod logs and the deployed app's endpoints.

● Sign-in is Ash's: a Keycloak device code in a browser, lost when a cloud
  container is reclaimed.
● `NODE_USE_ENV_PROXY=1` is load-bearing in a cloud session: Node's `fetch`
  ignores the proxy and could not resolve the deployed app's host.
● Self-update is off, so an update is a new commit of the bundle.
● **Never call upload, submit, resubmit, retry, add-on or environment
  variable tools without Ash's instruction each time.**

## Architecture

● `src/app.py`: app factory, CORS, two-tier rate limiting.
● `src/store.py`: atomic JSON store (deliberately not a database),
  anti-shrink merges, archive not delete, backups, migrations.
● `src/udl_client.py`, `src/udl_diagnostics.py`: UDL calls and the
  diagnostics probe.
● `src/orbits.py`, `src/family_elements.py`, `src/belt.py`, `src/cache.py`:
  orbital derivations, chart series, the GEO belt, a small TTL cache.
● `src/compendium_models.py`, `src/provenance.py`, `src/pol.py`,
  `src/graph.py`, `src/theatre.py`, `src/dossier.py`, `src/attention.py`,
  `src/comparison.py`, `src/briefing.py`: the compendium layers.
● `src/routes/`: the API; `src/routes/object_lists.py` generates the
  per-object CRUD and deliberately has no `from __future__ import
  annotations`.
● `src/logging_standard.py`, `src/gunicorn_conf.py`: logging.
● `scripts/` is outside `ruff check src tests` on purpose (vendored Script
  mode loader) but inside the Sonar mirrors.
● Credentials: `UDL_USERNAME` and `UDL_PASSWORD` from the environment, or
  `~/.config/phase_offset/credentials.ini` for local development only.

## Working in this repository

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # hash-locked, includes test tooling
cp .env.example .env
pytest --cov=src --cov-report=term-missing
python -m src.main                        # :8080, UI at http://localhost:8080/
```

`requirements.txt` is what the platform's test stage installs;
`requirements-runtime.txt` is what the image installs.
