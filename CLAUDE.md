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

## The Code Quality gate has five conditions, not one

Learned the hard way across 0.4.7, 0.4.8 and 0.8.2. The SonarQube gate fails on
any of these, and only the first produces anything resembling an error message:

● New issues = 0. The local mirror in `tests/test_sonar_contracts.py` covers
  the rules that have actually fired, including "Use logging.exception()
  instead", which fires on `logger.error` inside an `except` block and cost
  three upload cycles on its own because the gate's only visible message is
  "Quality Gate FAILED". It must scan `tests/` as well as `src/`,
  because `sonar-project.properties` sets `sonar.tests=tests`.
  It also covers "Refactor this exception test to have only one invocation
  possibly throwing an exception", which fires on a `pytest.raises` block
  holding more than one call: the test then passes if either raises, so a
  broken fixture builder satisfies a test written to prove a validator. Build
  the fixture first, assert on the one call under test.
● Coverage on new code. Measure the changed lines, not the project total: a
  95% project can still ship a poorly covered diff.
● **Duplicated lines on new code.** This one has no local check and is easy to
  trip: a new test file that copies an 11-line fixture from an existing one is
  duplicated enough to fail on its own. Shared fixtures live in
  `tests/conftest.py` (`make_seed_record`) for exactly this reason.
● Security hotspots reviewed. If this is the failing condition, no upload will
  ever fix it: a human must review them in the SonarQube user interface.
● **Coverage must be measurable at all, which means the release has to change
  a Python file inside `sonar.sources` (`src`).** This is a separate job,
  `code-quality-verify`, and it fails a build where SonarQube measured no
  coverage: "Code coverage was not measured for this build, so the coverage
  requirement was not applied." A docs-only or Dockerfile-only release trips it
  every time, and retrying cannot help because there is nothing to measure. A
  change under `tests/` does not count either: `sonar.tests=tests`, and
  coverage on new code is measured on sources, not tests. `bump_version.sh`
  warns when a release would land in this state. The route out is to bundle the
  change with a real source change, or to have the platform treat "nothing
  analysed" as a pass, which its own message already says it is.

  The job log confirms the mechanism. `code-quality-verify` checks that
  `.scannerwork/report-task.txt` exists, finds `sonar-quality-gate.json`,
  strips its whitespace and then tests it for the coverage condition. On the
  0.8.2 upload every one of those steps succeeded: the scan ran and the gate
  file was there. Only the coverage value was absent.

**Do not "fix" this one by reconfiguring coverage.** The theory that the report
does not line up with the analysed sources was tested at 0.8.2 and is wrong: the
pipeline's bare `pytest --cov` emits `<source>` at the repository root with
`filename="src/app.py"`, which matches `sonar.sources=src` exactly. Adding
`relative_files = True`, the usual internet advice, makes it strictly worse: the
report becomes `<source>src</source>` with `filename="app.py"`, which resolves
to a path that does not exist. Setting `source = src` alone drops the repository
root from the paths for no gain. Leave the coverage configuration alone.

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

**A mirror is only as good as its last miss.** The nested-ternary mirror went
green through 0.9.0 while the platform reported two nested ternaries, because
its two regexes exclude `{` and `}` so they cannot cross a template-literal
boundary, and the nesting was inside a `${...}` slot:
`a ? \`x ${b ? c : d}\` : \`y\``. Sonar reads the syntax tree, where a template
slot nests like anything else. A third pattern now covers that shape, and it
was calibrated the same way as the others: added first, confirmed to fire on
the unfixed file at the exact statement the platform named and on nothing
else, and only then was the code changed. Do that in that order every time,
or you have a test that passes rather than a mirror that works.

## The container image: three rules that are easy to undo

Set in 0.8.2 after a Container Scan failure, and **confirmed by the platform:
Container Scan passes on 0.8.2**, along with Secret Detection, Dependencies,
SAST, Dependency Scanning, Test, Container Build and the Code Quality scan
itself. Full account in `READINESS.md`, "Container Scan, worked 9 September
2026".

● **The base image is pinned by digest, in both `FROM` lines, and the two must
  always match.** The tag drifted between the build that passed Container Scan
  in August and the one that failed in September, so two builds of the identical
  archive scanned differently with nothing in the repository recording which was
  which. To refresh: pull the tag, read the digest, change both lines, rebuild,
  re-verify. Never change one of the two.
● **pip, setuptools and wheel are deleted from the runtime image, and the build
  fails if any survive.** Three copies ship by default and a cataloguer reads
  all three: the interpreter's site-packages, the wheel bundled in `ensurepip`,
  and the copy `python -m venv` puts in `/opt/venv`. Do not "fix" an installer
  advisory by upgrading pip; the image does not need pip at all.
● **A base image move must not move a package version.** 3.12 to 3.13 was done
  without regenerating a lock file, because the lock files are what Dependency
  Scanning reads and that gate cost six upload cycles. It worked because the
  existing hashes already covered the cp313 wheels, which was proven by
  installing `requirements-runtime.txt` under 3.13 with `--require-hashes`
  before the change was made. Prove it again the same way next time; if the
  hashes do not cover the new interpreter, that is a much larger change.

One standing caution: a Container Scan failure names vulnerable packages in its
advice text whatever the real cause. An Anchore policy fails only on a `STOP`
action, so read the policy evaluation and find the `STOP` row before changing a
version. A breakdown that says "90 findings, all WARN" and "the scan failed" is
describing two different things.

## There is no authentication, and that was a decision

Ash's instruction, 10 September 2026, after the shared team token cost three
releases of diagnosis: **remove it completely.** `TEAM_TOKEN`,
`require_team_token`, `/api/token-check`, the UI token box and every test for
them are gone in 0.9.0. The only secrets are `UDL_USERNAME` and
`UDL_PASSWORD`.

What that means, stated plainly rather than buried: **reads, writes and UDL
lookups are all open to anything that can reach the app.** The platform in
front of it is the access control. This is recorded as a decision, not a gap.

Three things follow, and undoing any of them quietly would be a regression:

● **`ALLOWED_ORIGIN` refuses `*` unconditionally.** It used to be conditional
  on a token being set, which was backwards: with writes ungated a wildcard
  origin is strictly more dangerous, because it would let any page on the
  internet issue writes from a reader's browser.
● **The strict rate limiter is now the only control on the UDL call budget.**
  It matters more than it did, not less.
● **`tests/test_ui_contracts.py` fails if token machinery reappears** in the
  interface, and `tests/test_security.py` asserts the open contract
  explicitly, so a 401 coming back has to be somebody's decision rather than a
  dependency creeping in.

Why it went, in one line worth keeping: a token generated the usual way is
always 43 characters, so two different values both read 43, and a single
non-breaking space picked up from a copy is one character and two bytes. Three
releases of diagnostics went into that before the answer turned out to be that
a shared string pasted into a browser tab was the wrong control for the job.
If authentication is ever needed here again, it needs identity from the
platform.

## Unclassified, publicly available information only

Ash's decision, 11 September 2026, answering the first open item in the
compendium specification. It is settled: **the compendium stays unclassified
and derived from publicly available information only.**

`src/classification.py` holds the marking and the handling statement in Ash's
own words. Do not invent, infer or elaborate a marking or a caveat scheme
here; a different one comes from the person who owns that decision.

The decision is enforced rather than described, because a note saying "open
sources only" constrains nobody:

● **An `internal_assessment` claim must cite the publicly available material
  it is derived from.** Every other source class already names something
  published, so a reader can follow the citation to the material. An
  analyst's own assessment is opaque about its inputs, which makes it the one
  place non-public material could enter unnoticed. It therefore carries the
  same citation burden a FACT does. `tests/test_compendium_models.py` proves
  it, and one test asserts that every declared source class is accounted for
  as public, derived-with-declared-basis, or the TBC placeholder, so adding a
  new class without thinking about the posture fails.
● **`GET /version` serves the marking.** The interface reads it rather than
  hard-coding a banner, so the string an analyst sees and the rule the
  validator enforces come from one module and cannot drift.

## Candidate systems: the catalogue grew, and the join is visible

`src/seed_data.py` still holds exactly the canonical 49, mirrored verbatim
from the spreadsheet. Seven more systems named in the research but absent
from it live in `src/candidate_systems.py`, and they are kept apart on
purpose: mixing them into the mirror would make it unverifiable against the
spreadsheet, because nobody could tell by looking which rows came from where.

Three rules make the difference structural, and `tests/test_candidate_systems.py`
enforces each:

● **No candidate carries a NORAD id or a launch year.** The research names
  behaviours, not catalogue entries. An invented satellite number is the one
  error in this domain that looks exactly like data: a chart would plot the
  wrong object and look entirely normal. The existing `SKIP_NO_NORAD_ID` path
  therefore excludes every candidate from charts and says so.
● **Every candidate cites its source and names who verifies it.** The
  TBC-with-an-owner rule from the compendium, applied to the catalogue.
● **A candidate is marked in the interface by text, not colour.** The badge
  reads "Candidate" and the provenance panel carries the source and the owner,
  read off the record rather than written into prose that could drift.

The seven are Luch/Olymp-1 and -2, COSMOS-2553, TJS-2, TJS-4, and SJ-6-05A
and -05B, all from the CSIS Space Threat Assessment 2025 by way of
`deliverable/research/02_domain_counterspace.md`. The SJ-6 pair is carried
because a proximity segment must name its counterpart, and the SY-24C
"dogfighting" segments need one.

**The store is at `schema_version` 3.** `_add_candidate_systems` is keyed on
`candidate_key`, a stable natural key, so it is idempotent by construction
rather than by a guard, and an existing deployment picks the seven up on its
next read. An analyst's edit to a candidate outranks the shipped text: only
the key is read, so a renamed, re-flagged or archived candidate is matched and
left alone. Proved by three deliberate sabotages, all caught: a non-idempotent
builder, a builder that clobbers an existing record, and a candidate that
quietly gains a NORAD id.

`launch_year` is now optional on the model because of this. Every one of the
canonical 49 still declares one and a test holds that, so the widening cannot
become a hole in the catalogue proper.

## The compendium layer: provenance is a schema, not a convention

Added in Phase 1 of the compendium upgrade (`deliverable/`, which carries the
research and the full specification). The catalogue holds static attributes.
This layer holds what behaviour data cannot supply, because the same manoeuvre
signature serves inspection, servicing and attack, and what resolves the
ambiguity is capability plus context plus pattern-of-life. That is the whole
analytical reason the tool exists.

`src/compendium_models.py` is the schema. Five things are load-bearing:

● **The claim is the atom.** Almost no domain field is a bare value. Each one
  is a `Claim`: statement, FACT / INFERENCE / SPECULATION, confidence, source
  class, citation, date, and who asserted it. A bare string is only for
  non-assertive data such as an id or a slug.
● **Two rules are validators, not review comments.** A FACT with no citation
  is rejected. A TBC with no named owner is rejected. Whitespace does not
  satisfy either. These are the failed research pass turned into code: an
  unverifiable claim has to name who must verify it.
● **`asserted_by` is required on every claim.** There is no login auth, so
  this field is the entire editorial layer. Do not make it optional.
● **Observability is not confidence.** `PatternOfLifeSegment.observability`
  says how well the behaviour could actually be seen (revisit rate, sensor
  coverage); `claim.confidence` says how sure we are the assessment is right.
  A segment from a sparse track and one from a dense track must never render
  identically. Same principle as the JCO HRR rank gate.
● **A proximity or pursuit mode must name its counterpart.** An RPO is always
  with something, and that counterpart is what drives the relative-motion
  view.

`src/store.py` is at `schema_version` 2. The compendium hangs beside
`systems`, never inside a record; `objects` is keyed by `system_id` so the
migration is idempotent by construction. `_add_compendium_layer` reads system
keys only, so it cannot alter a catalogue record even by accident. The
compendium CRUD is one generic collection-keyed API rather than six
near-identical sets, because six copies is six places for the anti-shrink
merge and the archive-not-delete rule to drift.

**How the migration was proved, and why two of the tests were wrong first.**
`tests/test_store_migration.py` builds a store in the exact shape the shipped
schema-1 code wrote, from the canonical 49 seed records, and compares every
field. It was then calibrated by deliberately breaking the migration twice:
once to drop a field, once to make the layer builder non-idempotent. The
first sabotage was caught. **The second was not**, because the idempotency
test compared the store file before and after a read, and a read migrates in
memory without writing, so it was comparing the file with itself. A second
attempt calling `_migrate` twice also failed to catch it, because the
`schema_version` guard makes the second call a no-op. Only calling
`_add_compendium_layer` directly catches it. Break the migration on purpose
before believing a migration test, every time.

## Provenance on screen: Phase 2 rules

The claims API is `src/routes/claims.py`, the vocabulary is `src/provenance.py`
and the interface renders it in the Provenance panel. Five things are
load-bearing:

● **An edit re-validates the whole claim.** `PATCH` merges anti-shrink and
  then runs the merged result through `Claim` again, so a patch cannot strip
  the citation off a FACT or the owner off a TBC. A rule enforced only at
  creation is decorative, and decorative provenance is worse than none
  because it looks like a guarantee.
● **The legend words are served, not hard-coded.** `GET /api/provenance/legend`
  carries the marker, confidence and source-class meanings. A copy in the
  interface would drift from the validators using the same vocabulary and
  nothing would fail. `tests/test_ui_contracts.py` asserts the legend text
  does not appear in the markup.
● **A chip states the strongest true thing, and a TBC is not its marker.** A
  browser run found an unsourced claim wearing an INFERENCE chip, with only a
  border colour marking it unverified: colour carrying the most important
  distinction alone. The chip now reads "TBC, re-verify" and what it was
  marked as moves to a meta row. `chipFace` owns this.
● **Four redundant encodings, never colour alone.** Colour, icon, text label
  and border style all carry the marker. The marker colours are existing house
  tokens, deliberately not the eight-slot series palette: those identify a
  satellite in a chart and an analyst must never read one as the other.
● **Only an http or https source URL becomes a link.** A citation is
  analyst-entered text, so `safeUrl` refuses anything else. Verified in a
  browser with a `javascript:` URL: no link is rendered and no script runs.

Claims are archived, never deleted, like everything else here: a withdrawn
assessment stays visible under `include_archived` so an analyst sees that a
claim was made and pulled rather than finding a silent gap.

**Family-level claims are not here on purpose.** They are modelled by
`FamilyAssessment`, a Phase 5 deliverable with its own required fields and its
own validation gate. Inventing a parallel family-claim store now would mean
migrating it away later.

## Phase 3, the pattern-of-life timeline: what must not be inferred

`src/pol.py` holds the mode vocabulary and the timeline assembler,
`src/pol_seed.py` the seeded history, `src/routes/segments.py` the API. The
timeline is the *assessed* behavioural history. The element-set charts are
the *raw* observed data from UDL. They are never drawn as the same thing.

Five rules, and three of them exist because a browser found them wrong:

● **An epoch is never more precise on screen than in the source.** The
  research says "May 2024", so the segment stores `2024-05` and
  `parse_pol_epoch` reports month precision, which the row states. Writing
  `2024-05-01` invents a day nobody observed.
● **An instant has no end.** The TJS-2 node read "2024 to ongoing", which
  asserts a behaviour still happening. `separation_event` and
  `anomalous_high_dv` are markers, not bands, and the server says which from
  the model's own frozenset.
● **A missing end is "no end recorded", never "ongoing".** SJ-21's 2022
  capture is finished, and read as ongoing purely because the field was
  blank. A blank field is not evidence of continuation. Where a source does
  say a behaviour continues, as for COSMOS-2558, that goes in the claim.
● **The server resolves the counterpart's name.** A client-side lookup
  rendered a raw uuid the moment a filter hid the other object. The browser
  only ever holds the page of the catalogue it is showing.
● **Colour on the timeline carries provenance, never the mode.** The
  eight-slot series palette identifies a satellite in a chart, and an analyst
  must never read one as the other. The marker tokens are reused, and the
  mode is carried in text.

A counterpart outside the catalogue keeps a `target:` slug and is labelled as
outside it. USA 314 is not one of our systems, and resolving it to something
shaped like a catalogue id would put a phantom object in front of an analyst.
Phase 5's `Target` records are where those become first class.

**The four CRUD endpoints are generated, not written twice.**
`src/routes/object_lists.py` builds read, create, edit and archive for any
per-object list, and claims and segments both use it. Two copies would put
the anti-shrink merge and the archive rule in two places, and would trip the
gate's duplicated-lines-on-new-code condition on its own. That module
deliberately has no `from __future__ import annotations`: FastAPI reads the
endpoint signatures at decoration time, and with postponed evaluation the
parameterised annotation is the string "model". mypy cannot follow a type
held in a closure, hence the four targeted ignores.

**The store is at `schema_version` 4.** `_add_pol_segments` is keyed on
`seed_key`, idempotent by construction, and skips a seed naming an object the
store does not hold rather than guessing.

**Still blocked, and not built:** the relative-motion view against a
counterpart outside the catalogue, which is [DECISION - Ash] item 5. It needs
a confirmed UDL path and query pattern for a target object's element sets,
and the specification warns against the per-object query-loop. SJ-25/SJ-21 is
buildable without it, because both are catalogued and the existing family
machinery already fetches them. COSMOS-2576/USA-314 is not.

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
● **Relative mode anchors on each object's latest element set, never its
  first.** Ash's rule, 10 September 2026. The question is "where has this come
  from to get where it is now", so now is the fixed point and history reads
  backwards from zero. It also keeps the baseline still: anchoring on the
  first point in the window made the same object at the same moment read
  differently at 30 days and at 90, because the baseline moved with the
  window. For longitude the wrapped step deltas are still summed first and
  the series is shifted afterwards, so a full-history drift right round the
  belt still reads +200 rather than -160. Verified in a browser against the
  table view: the last row is zero in every window, and the latest absolute
  value is identical across windows.
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

● **The panel plots one scope at a time, and says which.** Choosing a family
  plots the class; choosing a row in the catalogue plots that object's own
  history. Both go through one client-side loader and one server-side
  assembler, so the rank gate, the metric rule and the colour rule cannot
  drift between them. `/api/udl/object-elements` deliberately passes the whole
  family to `build_family_charts` and narrows with `focus_norad_id`, because
  colour is assigned from launch-order position in the family: a satellite
  charted alone keeps the colour it has beside its siblings. Only the focused
  object is fetched, so it costs one element-set lookup, not the family's.
● **Every message follows the scope on screen.** A single-object view that
  says "nothing in this family cleared the checks" describes the wrong thing.
  This is the fourth time a message in this UI has named something it could
  not see, and each one was caught in a browser rather than by reading the
  code. Drive the real page before believing any of them.

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
