# READINESS.md — UDL Tactics App (`legion`)

**Generated:** 20 August 2026
**Updated:** 20 August 2026, after the first real container build (see "Container build verification" below)
**Version at time of report:** 0.3.3 (`src/VERSION`); container verification run against 0.4.1, audit fix re-verified in-container at 0.4.2
**Scope:** pre-flight estimate per `app-store-readiness`. Not the platform's binding decision.

## Band: Not yet

One blocker, and it is not something local work can close: **the GitLab pipeline has never once run a stage successfully.** Every dimension below that *can* be verified locally now passes; the ones that require the actual platform runner remain unconfirmed until the `.gitlab-ci.yml` path fix (flagged to Koen, three lines: `dockerfile:`, `base-dir:`, and the `podman build -f` line, all still pointing at a `udl-tactics-app/` subdirectory that no longer exists) lands on `main` and a version upload actually clears Secret Detection.

**Score:** 14 of the 15 applicable dimensions pass locally (16 is N/A). Dimension 12, the pipeline, is the single outstanding fail. The band is capped at "Not yet" regardless of that score, because a red/never-run required pipeline is a blocker by the skill's own rule, and this report does not soften that.

## Per-dimension table

| # | Dimension | Result | Weight | Note |
|---|---|---|---|---|
| 1 | Verification loop green | **Pass** | blocker | 79 passed, 1 skipped (documented below), 0 failed, fresh venv |
| 2 | Coverage ≥ 80% | **Pass** | heavy | 95.9% |
| 3 | No secret in source/history | **Pass** | blocker | Grepped for credential-shaped strings; `.env.example` placeholder-only; fresh git history, one commit chain |
| 4 | Server contract: PORT/0.0.0.0/health/non-root/no ENV PORT | **Pass** | blocker | Confirmed live (smoke-tested as a running process, not just TestClient) |
| 5 | Container package flat at root | **Pass** | blocker | Verified in the actual zip: `Dockerfile`, `.gitlab-ci.yml`, requirements files all at root |
| 6 | Runtime hardened AND flattened (no setuid/setgid in layer history) | **Pass** | blocker | Built for real on 20 Aug 2026 (Docker 29.3.1, BuildKit). Image builds clean, 58 MB, runs as 10001:10001. Final filesystem carries zero setuid/setgid entries (`find / -xdev -perm /6000` returns 0) and no base-image history survives the scratch stage. One correction to the earlier claim: the final stage yields **two** layers, not one, because the trailing `WORKDIR /app` adds a 4.1 kB metadata layer after the single `COPY --from=prep / /`. That layer holds one directory and no setuid/setgid bit, so the scan property still holds |
| 7 | Coverage report at the gate's exact path | **Pass** | heavy | `coverage.xml` at root, matches `sonar-project.properties` and `.gitlab-ci.yml`'s `SONAR_SCANNER_OPTS` |
| 8 | Reproducible install, committed lockfile, no unaddressed CVE | **Pass** | heavy | Hash-locked via `pip-compile --generate-hashes`; verified clean install + full test run from a genuinely fresh venv on both `requirements.txt` and `requirements-runtime.txt`; `pip-audit` clean |
| 9 | Container: upload is a testable source tree, pipeline simulation green, emits coverage | **Likely (build now confirmed)** | blocker (container) | The container half is no longer theoretical: the image builds and serves live traffic (`/healthz` 200, `/readyz` 200 with a writable mount, 49 seeded records over `/api/systems`, token-gated writes, persistence across a restart). Simulated the platform's exact `pip install -r requirements.txt` + `pytest --cov --cov-report=xml:coverage.xml` sequence from a clean venv against the real package contents. Never run through the actual GitLab runner/podman - that's the pending blocker |
| 10 | Per-commit static analysis keeps violations at zero | **Likely** | heavy | `ruff check`, `ruff format --check`, `mypy --ignore-missing-imports`, `bandit` all clean. Not the exact SonarQube ruleset (no `sonar-scanner` access from this environment - CONTEXT-001 already documents this as a standing gap); this is the closest local approximation |
| 11 | Negative assertions classified per environment | **Pass** | blocker | One test (`readyz` 503-on-unwritable-storage) only holds under a non-root runner; explicitly `skipif(os.geteuid() == 0, ...)` with a reason, not silently deleted or left falsely passing |
| 12 | CI mirrors local loop, latest run green | **Fail (blocker)** | blocker | Zero of three upload attempts have cleared even Secret Detection. Root cause identified (stale `udl-tactics-app/` paths in `.gitlab-ci.yml`, confirmed byte-for-byte against two separate pastes of the file); fix handed to Koen, not yet landed |
| 13 | Version stamp + structured audit line, no secret in logs | **Pass** | medium | Both halves verified live in the container at 0.4.2, not asserted. `/version` returns 0.4.2. The audit trail was silently dropped up to 0.4.1 (no logging configured, so the audit logger had no handler and sat at WARNING); fixed by `configure_logging()` in `build_app`. An authorised PATCH and an archive through the running container each produced exactly one bare-JSON audit line on stdout, parsable without stripping a prefix, carrying event, sanitised actor, timestamp, record id and changed fields. No duplicates. Grepped the container log for the team token: zero hits |
| 14 | Accessibility to WCAG AA | **Pass** | medium | Fixed: label/`for` associations on every form control (were unassociated), `<main>` landmark, skip link, `aria-live` on the status message, `role="status"` on filter-result count. Computed contrast ratios for every text/background pair in use — one real failure found and fixed (`--text-faint` was 2.81:1, now 4.61:1). Structural/computed checks only; no live screen-reader pass run |
| 15 | Surgical structure, no dead code | **Pass** | medium | `ruff` clean, one unused import removed, one blind `except Exception` (masking real errors as 429s) fixed to catch the specific exception |
| 16 | House voice in user-facing copy | **N/A** | light | Internal analyst tool, not customer-facing copy |

## Blockers (must clear before "Ready")

1. **The GitLab pipeline has never run successfully.** Owner: `ci-cd`, `appstore-gate-compliance`. Fix: land the three-line `.gitlab-ci.yml` correction (already handed to Koen) and get one clean upload through Secret Detection onward. Nothing else in this report can substitute for a real green run.
2. ~~**Container flattening is unverified.**~~ **Closed, 20 August 2026.** The three-stage Dockerfile builds and the image runs. Detail below.

## What would raise the band

● Blocker 1 clearing (a real green pipeline run) moves this to **Likely after fixes**.
● Blocker 2 is now closed: the flattened Dockerfile builds and the image serves traffic.
● Dimension 13 is back to a pass: the dropped audit line is fixed and verified in-container.
- Once both clear, re-run this check: if dimensions 9 and 10 are confirmed against the real runner (not just simulated), the band moves to **Ready**.

## Container build verification, 20 August 2026

The one thing the previous pass could not do. Recorded here so it does not have to be rediscovered.

**Environment:** Docker 29.3.1 with BuildKit, daemon started inside the Claude Code session container. Base image `python:3.12-slim`, digest `sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a`, pulled through `mirror.gcr.io` because this sandbox's egress policy denies Docker Hub's blob CDN (`production.cloudfront.docker.com`, 403 on CONNECT) while allowing the manifest host. The mirror serves Docker Hub content at identical digests, so the base image is the real one.

**One deviation from the committed Dockerfile, and why it cannot affect the result.** This sandbox re-terminates TLS, so `pip install` inside the build failed certificate verification. The build was run from a generated variant that adds three lines to the `build` stage only: copy the proxy CA, `update-ca-certificates`, and `PIP_CERT`. Nothing but `/opt/venv` leaves that stage, so no added instruction can reach the final image. The committed `Dockerfile` is unchanged and every other stage, including the `prep` sweep and the `scratch` flatten, was built exactly as committed. On a runner with normal PyPI access the committed file needs no such change.

**What passed.**

● Build succeeds end to end, 34 seconds cold, image 58 MB.
● Final image: `USER 10001:10001`, `WORKDIR /app`, no `ENV PORT`, `EXPOSE 8080`.
● Zero setuid/setgid entries anywhere in the final filesystem.
● `docker history` shows only the scratch stage's own instructions. No base-image layer history survives.
● Starts under gunicorn with the uvicorn worker, binds `0.0.0.0`.
● Honours an injected `PORT`: with `PORT=9090` it listened on 9090, confirming the platform contract.
● `GET /healthz` 200, `GET /version` 200 reporting 0.4.1, `GET /` serves the 17.9 kB admin UI.
● With a writable mount at `STORAGE_MOUNT_PATH`: `/readyz` 200 with `storage_writable: true`, and `/api/systems` returns all 49 seeded records.
● Writes gated as designed: PATCH with no token 401, with a wrong token 401, with the right token 200.
● Persistence proven across a container restart: the patched note survived.

**Two findings the build turned up. Both now closed.**

1. **The audit line was silently dropped. Fixed in 0.4.2.** Nothing configured logging, so the audit logger had no handler and sat at WARNING, and every `audit_logger.info(...)` was discarded. A real authorised PATCH through the 0.4.1 container produced no audit output at all, meaning the create/update/archive trail had been absent for the life of the project. `configure_logging()`, called from `build_app()`, now attaches one stdout handler to the parent `udl_tactics_app` logger, with an audit-aware formatter so audit records emit as the bare JSON line they already are. The audit logger is pinned to INFO so `LOG_LEVEL` cannot silence a compliance record.

   Re-verified in the 0.4.2 container: a PATCH and an archive each produced exactly one parsable JSON line, no duplicates, and the team token appears nowhere in the log. Nine tests cover it, each asserting on what a real handler writes to its stream. Worth noting why the old tests missed this entirely: they asserted through `caplog`, which installs its own root handler, so the trail appeared to work under test and only under test.

2. **The `/app/data` fallback is by design. Confirmed by Ash, 20 August 2026: the file-storage add-on will always be present.** `_resolve_data_dir()` falls back to `Path.cwd() / "data"`, which is `/app/data`, and `/app` is root-owned 0755 while the process runs as 10001, so with no `STORAGE_MOUNT_PATH` every read returns 500 and `/readyz` reports 503. That path is not reachable in deployment: the add-on always supplies a writable mount. No code change made. If the add-on assumption ever changes, the options are to `mkdir` and `chown 10001` an `/app/data` in the `prep` stage, or to refuse to start when `STORAGE_MOUNT_PATH` is unset, which fails loudly rather than per-request.

**What still could not be verified here.** The `prep` stage's `apt-get update && apt-get -y upgrade` failed with 403 Forbidden on `deb.debian.org`, again this sandbox's egress policy, and the `|| true` swallowed it by design. So the OS patch layer applied nothing in this build and remains untested. It should work on the real runner, but treat it as unverified until a build with mirror access confirms it.

## Skills consulted for this pass

`app-store-readiness` (this report), `toolchain-adapters` (Python command mapping), `dependencies` (lockfile standard), `testing-standards` (environment-scoped assertions), `observability-and-audit` (audit line, readiness probe), `accessibility` (audit checklist, contrast computation), `security-hardening`, `app-store-deployment`, `deploy-recipes`, `code-architecture`, `packaging`, `data-layer`, `api-and-integration`.

Not consulted, and worth a look if anything above regresses: `ci-cd` (pipeline structure itself, beyond the path fix), `release-and-deploy` (the deploy-gate step once a build actually succeeds), `environment-setup` (if this needs to run on a fresh machine from scratch).

## Honesty note

This report was generated retroactively, after three failed upload attempts, not from scaffold time. That is itself the finding worth remembering: several of the fixes above (the audit line, the readiness probe, the hash-locked lockfile, the accessibility pass) are exactly the kind of thing `app-store-readiness` is built to catch *before* a first submission, cheaply, rather than reactively after a review finds them. Next project on this baseline: run this skill at scaffold time, not after the third failed pipeline.
