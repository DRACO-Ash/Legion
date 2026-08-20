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

**Not verified, flagged honestly in `READINESS.md`:**
- **The container build.** The Dockerfile was restructured to a
  `FROM scratch` + single `COPY --from=prep / /` final stage (flattens the
  image to one layer, so the Anchore scan can't find a setuid/setgid bit in
  layer history even after the existing `chmod` sweep). This was never
  built — the environment that produced it had no Docker daemon. **If you
  have Docker/Podman available, building this for real and confirming it
  runs is the single highest-value thing to check first.**
- The GitLab pipeline itself, obviously, per the blocker above.

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
