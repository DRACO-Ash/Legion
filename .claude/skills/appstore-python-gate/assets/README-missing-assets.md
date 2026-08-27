# Missing assets

`SKILL.md` cites three templates. The uploaded package (`files_9.zip`) was
flattened and carried none of them.

● `pyproject.toml.template` has been reconstructed here, copied verbatim from
  section 5 of `references/package-contract.md`, where it is reproduced in full.
● `Dockerfile.template` (digest-pinned base, non-root, fail-closed patch step,
  runtime-only install under `--require-hashes`) is **absent** and has not been
  invented. Fetch it from the source of the skill.
● `dockerignore.template` is **absent** for the same reason.
