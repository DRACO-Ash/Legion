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
- **No application-level authentication.** Every route is open. The shared
  team token was removed in 0.9.0: it cost more operator time to diagnose than
  it protected, and it gated the UDL lookups the charts exist to draw. Access
  control belongs to the platform in front of this app. The only secrets are
  `UDL_USERNAME` and `UDL_PASSWORD`, which never leave the process.
- **Charts follow the selection.** Choosing a family plots the whole class;
  choosing one row in the table plots that object's own history. Same rules
  either way: JCO HRR rank 0 to 3 only, one metric per axis, and a satellite
  keeps its colour in both views.

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
| `POST /api/systems` | none | Add a new tracked system |
| `PATCH /api/systems/{id}` | none | Anti-shrink update |
| `DELETE /api/systems/{id}` | none | Archive (not delete) |
| `GET /api/udl/jco-hrr?common_name=&window_hours=` | none | Search live UDL JCO HRR feed by name |
| `GET /api/udl/jco-hrr/{sat_no}?window_hours=` | none | Look up one JCO HRR entry by satNo |
| `GET /api/udl/elset/{sat_no}` | none | Latest element set for a satNo |
| `GET /api/udl/clash-check?window_hours=` | none | Resolves the COSMOS-2612/2613/2614 NORAD 68762 clash against live UDL |
| `GET /api/udl/family-elements?family_id=&window_days=` | none | Element-set tracks for every rank 0-3 member of one family, ready to chart. `window_days=0` means the full history |
| `GET /api/udl/object-elements?record_id=&window_days=` | none | The same, for one catalogued object. Same rank gate, same metric rule, same colour |

**There is no authentication.** Reads, writes and UDL lookups are all open to
anything that can reach the app. That is a deliberate decision taken on
10 September 2026, not an oversight: the shared bearer token that used to gate
the writes and the UDL routes was removed because diagnosing it repeatedly cost
more than it protected, and because it blocked the element-set lookups the
application exists to serve. The catalogue is public-domain reference data.

What still protects the things worth protecting:

- **The UDL credentials** never leave the process and appear in no response.
- **The UDL call budget** is held by a strict in-process rate limiter, which is
  now the only control on it and therefore matters more than it did.
- **`ALLOWED_ORIGIN` must be explicit.** The app refuses to start on `*`,
  unconditionally. This used to be conditional on a token being set, which was
  the wrong way round: with writes ungated, a wildcard origin would let any
  page on the internet issue them from a reader's browser.

If an application-level control is ever wanted again, it should be real
identity passed down from the platform, not a shared string pasted into a
browser tab.


**Why it went, in one paragraph, so nobody rebuilds it.** A shared token
generated the usual way is always 43 characters, so two different values both
read 43 and a length comparison cannot separate them. Worse, a single
non-breaking space picked up by copying through a document counts as one
character and two bytes, so both sides report the same length and the compare
still fails. Three releases went into diagnostics for that: length reporting,
then byte reporting, then a dedicated `/api/token-check` endpoint. All of it
was machinery for a control that was never the right shape for the problem. If
this application needs authentication again, it needs identity from the
platform, not a string an analyst pastes into a tab.


## Branding and icons

The browser tab reads **Legion · Tracked Systems**. The favicon and every icon
in the interface are inline SVG in `src/static/index.html`: the tab icon as a
plain (not base64) data URI on the `<link rel="icon">`, and the rest as one
`<symbol>` sprite referenced by `<use>`. Nothing is fetched, so it works
offline, survives any content-security policy, and does not leave the browser
asking for a `/favicon.ico` that is not there.

The mark beside the title is a placeholder: an orbit motif in the Bluestaq
palette, not the official Legion artwork. To swap in the real thing, replace
the `i-mark` symbol's contents and the `rel="icon"` data URI with the supplied
paths. Note the App Store listing icon is uploaded separately in the store's
own interface and is not part of this package.

Icons are decorative throughout: each sits beside text that already says the
same thing and carries `aria-hidden="true"`. The one place an icon does work is
the status pill, where a filled, dimmed, open or dashed dot means state is
readable without relying on colour.

## Reading the catalogue

The table shows **15 rows a page** by default, with Previous and Next below it
and a "Showing 16 to 30 of 49 systems" line above. The Rows control offers 10,
15, 25, 50 or All, and the choice is remembered per browser. Filtering or
reordering returns you to the first page, since page three of a different
ordering is a different set of rows, and a filter that shrinks the list past
your current page clamps rather than rendering an empty table.

Paging is client-side, and deliberately so: sorting is client-side too, and
splitting them would slice page two out of the server's order and then sort
only that slice, so a page would show the wrong rows. At this scale, tens of
hand-entered records, the browser is the right place for both. If the
catalogue ever runs to thousands, sorting and paging move to the server
together, not one at a time.

Every column in the catalogue table sorts: click a heading once for ascending,
again for descending. Launch year and NORAD ID sort numerically, status sorts
by operational order (on-orbit, decaying, decayed, unconfirmed) rather than
alphabetically, and a record with no value in the sorted column always lands at
the bottom rather than at whichever end the sort is pointing. Sorting happens in
the browser against the rows already fetched, so it costs no request and holds
through filtering.

## Family movement charts

**Three gates stand between an analyst and a chart, and all three have to be
open.** The panel names the ones it can see on load rather than making you
guess:

1. `UDL_USERNAME` and `UDL_PASSWORD` in the deployment's Configuration tab.
   Element sets come from live UDL; without them every chart route answers 503
   "UDL is not configured".
2. A JCO HRR rank of 0 to 3 on the object itself. A family whose members are
   all rank 4 or 5, or all absent from the feed, produces no chart and lists
   each object with the reason.

The catalogue works without any of them; only the charts need them.

The panel plots a whole family's element sets together,
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
- There is no per-analyst identity, and since 0.9.0 no application-level
  authentication at all. Every route is open to anything that can reach the
  app. Recorded here as an accepted, deliberate limitation: the platform in
  front of the application is the access control.
