# UDL Tactics App

Queries the Unified Data Library (UDL) JCO HRR high-interest feed and element
sets. Built for the Bluestaq App Store (server archetype, Python template).

## Status

69 tests passing, 95% coverage, `pip-audit` clean. Smoke-tested as a real
running process (not just in-process TestClient): live HTTP calls proved
auth gating, the anti-shrink PATCH merge, archive-not-delete, and that data
survives a process restart. Not yet deployed - App Store submission needs
the App Store MCP tooling and a real git repo, which this build environment
doesn't have. Hand this to Claude Code for that step.

**Not verified against live UDL** (no network path to UDL from the build
sandbox). Endpoint paths and field names in `src/udl_client.py` are copied
from CONTEXT-001's LEARNED register (FACT), but two things are flagged as
INFERENCE in that file's docstrings and need a live check before trusting
them beyond a smoke test:

1. Whether `/udl/elset` accepts a direct `satNo=` equality filter.
2. The notification window semantics (does `window_hours` return the full
   current baseline, or only deltas created in that window).

## What's new: a persistent, editable catalogue

`GET /` now serves a form-based admin UI (`src/static/index.html`) over a
persistent tracked-systems store, seeded from the same 49 systems in
`tactics_wiki.html` (mirrored verbatim, per data-layer - the delivered
spreadsheet's values are law, not re-canonicalised). Analysts can add,
edit, and archive systems as new ones are found; the live UDL clash-check
and elset lookup from the previous build stay as-is for enrichment.

- **Store**: atomic JSON file (`src/store.py`) on the App Store file-storage
  add-on (`STORAGE_MOUNT_PATH`), per data-layer's default for low-concurrency,
  no-relational-query state. Temp-write-then-rename, schema-versioned,
  forward-migrating, backed up before an archive (pruned to the last 10).
- **Anti-shrink updates**: `PATCH /api/systems/{id}` merges only the fields
  sent; nothing you don't touch is ever cleared.
- **Archive, not delete**: `DELETE /api/systems/{id}` sets `archived: true`
  rather than removing the record, so a retired object stays auditable.
- **Auth**: reads (`GET`) are public; writes (`POST`/`PATCH`/`DELETE`) need
  the same `TEAM_TOKEN` bearer auth as the UDL routes. The UI has a token
  field (stored in `sessionStorage` for that browser tab only) - paste it
  once to enable add/edit/archive.

## Local setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # includes test tooling - see note below
cp .env.example .env   # fill in UDL_USERNAME/UDL_PASSWORD or rely on
                        # ~/.config/phase_offset/credentials.ini [udl]
pytest --cov=src --cov-report=term-missing
python -m src.main     # runs on :8080, catalogue UI at http://localhost:8080/
```

**Two requirements files, per the App Store contract (CONTEXT-001 Section 7):**
the platform's TEST stage only ever runs `pip install -r requirements.txt` then
pytest, so `requirements.txt` has to carry pytest/pytest-cov/respx/pip-audit as
well as the runtime deps. `requirements-runtime.txt` is the lean, test-tooling-free
file the Dockerfile actually installs into the image. Add a new runtime
dependency to `requirements-runtime.txt`; add a new test-only dependency to
`requirements.txt` directly.

## Endpoints

| Route | Auth | Purpose |
|---|---|---|
| `GET /` | none | Admin UI: browse, filter, add, edit, archive tracked systems |
| `GET /healthz` | none | Liveness |
| `GET /readyz` | none | Readiness; reports `udl_configured` boolean only |
| `GET /api/systems?nation=&regime=&status_filter=&q=&include_archived=` | none | List/filter the catalogue |
| `GET /api/systems/{id}` | none | One record |
| `POST /api/systems` | Bearer team token | Add a new tracked system |
| `PATCH /api/systems/{id}` | Bearer team token | Anti-shrink update |
| `DELETE /api/systems/{id}` | Bearer team token | Archive (not delete) |
| `GET /api/udl/jco-hrr?common_name=&window_hours=` | Bearer team token | Search live UDL JCO HRR feed by name |
| `GET /api/udl/jco-hrr/{sat_no}?window_hours=` | Bearer team token | Look up one JCO HRR entry by satNo |
| `GET /api/udl/elset/{sat_no}` | Bearer team token | Latest element set for a satNo |
| `GET /api/udl/clash-check?window_hours=` | Bearer team token | Resolves the COSMOS-2612/2613/2614 NORAD 68762 clash against live UDL |
| `GET /api/udl/family-elements?family_id=&window_days=` | Bearer team token | Element-set tracks for every rank 0-3 member of one family, ready to chart. `window_days=0` means the full history |

Auth is a shared bearer token (`TEAM_TOKEN`), compared in constant time. It
fails closed: with no token configured, every write and every UDL route
answers 503 rather than running open. Set it, together with `ALLOWED_ORIGIN`
(the app refuses to start on a wildcard origin with a token set), before the
app is of any use beyond reading the catalogue.

## Reading the catalogue

Every column in the catalogue table sorts: click a heading once for ascending,
again for descending. Launch year and NORAD ID sort numerically, status sorts
by operational order (on-orbit, decaying, decayed, unconfirmed) rather than
alphabetically, and a record with no value in the sorted column always lands at
the bottom rather than at whichever end the sort is pointing. Sorting happens in
the browser against the rows already fetched, so it costs no request and holds
through filtering.

## Family movement charts

The panel below the catalogue plots a whole family's element sets together,
which is the only scale at which a class's behaviour is visible: one satellite
drifting means little, six of them drifting the same way is a pattern.

- **Only objects at JCO HRR rank 0 to 3 are pulled.** The catalogue decides
  which objects are Red; the JCO HRR feed decides which are worth pulling
  element sets for. Rank 4 and 5 entries are not fetched at all, and neither
  is an object missing from the feed, because "ranks 0 to 3" cannot be
  satisfied by an object carrying no rank. One feed call ranks the whole
  family, and anything excluded is named under the chart with the rank that
  excluded it, so a gap is never silent. If the feed itself fails the request
  fails: a data-quality gate that cannot be applied must stop the pull rather
  than wave it through.
- **The window runs to the full history.** Seven, thirty, ninety or a hundred
  and eighty days, or everything UDL holds. The full history is the absence of
  an epoch filter, not a very wide one. A series longer than a thousand
  element sets is thinned to a thousand evenly spaced points for the plot,
  first and last always kept, and says so; the drift rate is measured on every
  element set before any thinning.
- **GEO members are charted on mean longitude**, derived from the element set
  as `RAAN + argOfPerigee + meanAnomaly - GMST(epoch)`. UDL carries no
  longitude field, so this is an approximation - sound for a near-circular,
  near-equatorial orbit, which is what station-keeping means in practice.
  Good for drift, station-keeping and one object closing on another; not for
  conjunction assessment. Drift is summed step by step rather than taken from
  first to last, so an object that has drifted right round the belt over
  several years still reports the rate it actually drifted at.
- **Everything else is charted on mean motion**, in revolutions per day,
  exactly as UDL reports it. A step change is an orbit change; a steady slope
  is decay.
- A satellite catalogued as GEO but no longer moving like one - a decayed or
  manoeuvred object - moves to the mean-motion chart automatically, because a
  longitude derived from a non-synchronous orbit is a meaningless number that
  still reads like a position.
- The two never share an axis. A family holding both kinds of object gets two
  charts stacked.
- **Absolute** shows where the class is parked. **Relative to window start**
  re-bases each satellite to its own first element set, which is what makes
  drift legible when a family is spread across 200 degrees of the belt.
  Switching between them redraws data already fetched; it costs no UDL call.
- Each chart carries a legend with each satellite's latest value and drift
  rate, a hover tooltip, and a table view holding every plotted value.

## Credentials

Precedence: `UDL_USERNAME`/`UDL_PASSWORD` env vars first (required for the
App Store deployment - `security-hardening`'s env-only config contract),
then a local-dev-only fallback to `~/.config/phase_offset/credentials.ini`
section `[udl]`, matching the convention already used by the Script-mode
tools. The credentials.ini path is never present inside the built container,
so the fallback simply never fires there.

## Deploying

Not done in this build session. The remaining steps, per your org's
`getting-started` / `app-store-deployment` skills:

1. `docker build` and run the pipeline simulation (needs Docker; unavailable
   in this build sandbox).
2. `engineering-reviewer` and `security-reviewer` gates.
3. `deploy-gate`, then `upload_package` / `save_env_vars` / `apply_env_vars`
   / `submit_app` via the App Store MCP tooling (unavailable here).

## Known simplifications

- Rate limiting is an in-memory per-process limiter (stdlib only, no new
  dependency) - resets on restart and doesn't share state across replicas.
  Fine for a first release; revisit if this ever runs multi-replica.
- `/udl/elset` lookups assume the first list item is the most recent element
  set; unconfirmed against live UDL.
- The chart history comes from `/udl/elset/history` with a `satNo` and an
  `epoch` range filter. UDL publishes a `/history` sub-resource on its
  collections as a general pattern, but this specific path and these
  parameters are inference, not verified fact. If UDL answers 4xx the app
  falls back to the single latest element set, so the chart still draws - one
  point per satellite instead of a track. `/readyz` will not tell you which
  happened; the line under the chart controls will.
- Charts carry at most eight satellites, the number of colours in the
  validated categorical palette. A ninth would be indistinguishable from an
  existing line under colour-vision deficiency, so a larger family lists the
  remainder as "not charted" instead. No seeded family is that large.
- Element sets are cached in-process for two minutes per satellite, per
  worker, so switching between families does not re-run the same lookups.
- The JSON store is single-writer per process (per data-layer's decision
  rule) - fine for a handful of analysts, but move to the Postgres add-on
  if concurrent writers or relational queries become a real need.
- The team token is a single shared secret (no per-analyst identity), same
  shared-token model as the rest of this baseline's server archetype -
  recorded here as an accepted limitation, not an oversight.
