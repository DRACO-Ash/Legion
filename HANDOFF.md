# HANDOFF.md — full history and context, moving from Claude.ai to Claude Code

**Written:** 20 August 2026, at the point of moving this project's primary
development from a Claude.ai chat session into Claude Code with a new GitHub
repository. Purpose: nothing decided or discovered so far should have to be
rediscovered. `CLAUDE.md` is the short version read every session; this is
the long version, read once, on arrival.

## How this project came to exist

Started as a request to build a "Tactics Wiki" — a static HTML reference for
Russian and Chinese ASAT/RPO satellite systems, sourced from
`Red_ASAT_Systems.xlsx`. That artefact (`tactics_wiki.html`) still exists
and is the canonical source for the 49 seeded systems — see
`src/seed_data.py`, which mirrors its `DATA` array verbatim.

From there: "let's build this into an app where we can query the UDL" →
a FastAPI service → "let's make it so we can update it with new
information" → a persistent, editable catalogue with an admin UI. Then
versioning, then App Store deployment — which is where most of the pain
below happened.

## The App Store deployment saga — what went wrong, in order

This is worth reading in full before touching anything App-Store-related,
because each failure looked different on the surface but the underlying
lesson repeats: **verify against the real thing, not the working
directory's cached state.**

### 1. Backwards requirements files (fixed)

The platform's TEST stage runs exactly `pip install -r requirements.txt`
then `pytest --cov`. The first build had test tooling (pytest, pytest-cov,
respx) in `requirements-dev.txt` and runtime-only deps in `requirements.txt`
— backwards. Result: `pytest: command not found`, exit 127. Fixed by
swapping the files' roles: `requirements.txt` now carries everything the
TEST stage needs; `requirements-runtime.txt` is the lean file the Dockerfile
actually installs. Verified by installing each into a genuinely fresh venv
and running the exact platform command against it — not just trusting the
file contents looked right.

### 2. Zip packaging nested in a subdirectory (fixed)

The very first zip upload had everything under a `udl-tactics-app/` folder
instead of flat at the zip root. The App Store's container template
detection needs `Dockerfile` at the package root — a nested one "defeats
template detection and breaks the build context." Fixed: `zip -r archive.zip
.` from inside the project directory, not `zip -r archive.zip project-dir/`.

### 3. `.gitlab-ci.yml` baked in the stale nested path — the real, still-open blocker

This is the one that cost three upload cycles to fully understand, because
each failure looked like a new problem:

- Upload 1: failed before any pipeline stage ran. Diagnosis at the time:
  looked like a runner/infrastructure fault (a Go runtime panic,
  "Failed to allocate signal stack for domain 0" in an unrelated SAST
  scanner job) — a red herring, coincidental infra flakiness on that run.
- Upload 2: `pytest: command not found` — this was issue #1 above, fixed.
- Upload 3: zip corrected (flat structure), but the App Store's pipeline
  **still** failed with "no `udl-tactics-app/Dockerfile` found," quoting a
  path that hadn't existed in any zip since fix #2.

The actual root cause, confirmed by getting the real `.gitlab-ci.yml`
content pasted back twice, byte-for-byte identical both times: the file
that governs the GitLab pipeline is **not** part of what a version-upload
zip touches. It was auto-generated once, at initial onboarding, when the
very first (nested) upload existed — and it baked `udl-tactics-app/` into
three places (the Anchore `dockerfile:` input, the SonarQube `base-dir:`
input, and the `podman build -f ... -f udl-tactics-app/Dockerfile
udl-tactics-app/` line). Every subsequent zip fix was invisible to the
pipeline, because **re-uploading a new version does not update
`.gitlab-ci.yml`** — that file only changes via a direct commit to the
GitLab repo itself.

A separate "helpful" report at one point suggested deleting
`.gitlab-ci.yml` entirely to fall back on a platform default template.
**This was correctly rejected** — the file has real, specific deploy logic
(a GitOps push to a specific Harbor path, an ArgoCD values-file patch for
`application/appstore-legion/helm-values.yaml`) that a generic template has
no way to replicate. Deleting it would likely produce a green pipeline that
built a container and deployed it nowhere useful.

**Current status:** the three-line fix has been identified and handed to
**Koen**, the engineering lead with access to that GitLab repo, via a Teams
message, asking him to either make the edit directly on `main` or grant
write access. As of this handoff, **this has not yet been confirmed done.**
Check before assuming it's resolved. The exact three lines, current →
corrected:

```
dockerfile: udl-tactics-app/Dockerfile   →   dockerfile: Dockerfile
base-dir: udl-tactics-app/               →   base-dir: .
-f udl-tactics-app/Dockerfile udl-tactics-app/   →   -f Dockerfile .
```

A full corrected copy of `.gitlab-ci.yml` is committed in this repo for
reference — but remember, per the point above, **committing it here does
nothing to the actual GitLab repo.** Someone with access has to apply it
there directly.

### 4. The readiness audit — a direct question exposed real gaps

Partway through, asked directly: "have you used all the skills to get this
in the best place to pass the App Store?" Honest answer at the time: no.
Running the actual `app-store-readiness` skill (designed for exactly this)
found several real, previously-unaddressed gaps, all fixed in the same
pass:

- No lint/type-checking had ever been run (`ruff`, `mypy`) — found a blind
  `except Exception` that would have silently mislabelled any real bug as
  a 429 rate-limit response.
- No structured audit logging on privileged actions (create/update/archive)
  — added, per Bluestaq's `observability-and-audit` standard.
- `/readyz` reported a boolean without ever proving storage was actually
  writable — added a real write-then-delete probe (an existence check
  alone can pass on a root-owned, read-only mount and only fail on the
  first real write, per `appstore-gate-compliance`'s own failure catalogue).
- Dependencies were exact-pinned but not hash-locked — regenerated via
  `pip-compile --generate-hashes`, verified installing clean in a fresh venv
  before adopting.
- The container wasn't hardened against the specific way Bluestaq's Anchore
  scan reads layer history (`suid_or_guid_set` can still be flagged even
  after an in-place `chmod` sweep, because the scan reads per-layer diffs).
  Restructured to a flattened, single-layer final stage — **but this could
  not be build-tested**, because the environment doing the work had no
  Docker daemon. This is the first thing to verify for real once Docker is
  available.
- The admin UI's form labels were never actually associated with their
  inputs (no `for=` attribute) — an accessibility bug that had been present
  the whole time. Fixed, along with a landmark, a skip link, a live region,
  and one real WCAG contrast failure (2.81:1, needed 4.5:1) found by
  actually computing the ratios rather than eyeballing the palette.

Full detail and the current pass/fail table: `READINESS.md`. **Band: Not
yet** — capped by the still-open GitLab pipeline blocker, regardless of how
much local verification passes.

## What to do first in Claude Code

1. Read `CLAUDE.md`, then this file, then `READINESS.md`.
2. Check with Ash/Koen on the `.gitlab-ci.yml` fix status before assuming
   it's landed.
3. **If Docker/Podman is available: build the container for real.** This
   was the one thing that couldn't be verified before. `docker build -t
   udl-tactics-app:test .` from the repo root, then `docker run -p
   8080:8080 udl-tactics-app:test` and hit `http://localhost:8080/healthz`.
   If that works, update `READINESS.md`'s dimension 6 and 9 from "unverified"
   to a real pass/fail.
4. Set up the GitHub remote and push — the local git history (one line per
   version, `v0.3.1` through `v0.4.0`) is already in the repo; don't
   re-init, just add a remote and push.
5. Once the GitLab pipeline fix lands, get one real upload through and
   update `READINESS.md` accordingly — that's the actual gate, not any of
   the local verification above.

## Things not to relitigate

These were genuine back-and-forth decisions, already settled — revisit only
with new evidence, not by re-deriving from scratch:

- **JSON file store, not a database**, for the tracked-systems catalogue.
  Deliberate, matches Bluestaq's data-layer default for low-concurrency,
  non-relational state.
- **Archive, not delete**, for removed systems.
- **Shared team-token auth**, not per-analyst identity — an accepted
  simplification, recorded as such in the README, not an oversight.
- **The two-requirements-file split** — this looks redundant until you
  read why (see saga item #1 above). Don't merge them back into one file.
