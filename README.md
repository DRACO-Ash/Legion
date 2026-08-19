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

Auth is a shared bearer token (`TEAM_TOKEN`), compared in constant time. Unset
locally, all write routes run open (loopback-only assumption); set it before
hosting for a team, together with `ALLOWED_ORIGIN` (the app refuses to start
on a wildcard origin with a token set).

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
- The JSON store is single-writer per process (per data-layer's decision
  rule) - fine for a handful of analysts, but move to the Postgres add-on
  if concurrent writers or relational queries become a real need.
- The team token is a single shared secret (no per-analyst identity), same
  shared-token model as the rest of this baseline's server archetype -
  recorded here as an accepted limitation, not an oversight.
