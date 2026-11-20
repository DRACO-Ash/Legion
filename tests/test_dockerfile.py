"""The container image's rules, held as tests rather than as prose.

Every rule here was written down in CLAUDE.md after it cost an upload, and a
rule that lives only in prose is one edit away from being undone. These read
the committed Dockerfile; the image itself was built and run to verify the
same things, and READINESS.md records how.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")

# Traced inside the base image, 20 November 2026: every package whose shared
# libraries the interpreter or a compiled wheel loads, plus what the build and
# the CMD themselves run. Purging any of these would break the container.
NEEDED = frozenset(
    {
        "libc6",
        "libssl3t64",
        "libgcc-s1",
        "gcc-14-base",
        "zlib1g",
        "libffi8",
        "libbz2-1.0",
        "liblzma5",
        "libzstd1",
        "dash",
        "dpkg",
        "coreutils",
        "findutils",
        "passwd",
    }
)


def _purged() -> list[str]:
    match = re.search(r"set -- (.*?);", DOCKERFILE, re.DOTALL)
    assert match, "the purge step's package list was not found"
    return match.group(1).replace("\\", " ").split()


def test_both_stages_use_the_same_pinned_digest():
    digests = re.findall(
        r"^FROM python:[^@\s]+@(sha256:[0-9a-f]{64})", DOCKERFILE, re.MULTILINE
    )
    assert len(digests) == 2, "both FROM lines must pin a digest"
    assert digests[0] == digests[1], "the two FROM lines must never differ"


def test_the_purge_never_removes_a_package_the_runtime_needs():
    assert set(_purged()) & NEEDED == set()


def test_the_purge_removes_what_the_scan_flagged_and_nothing_loads():
    expected = {
        "util-linux",
        "mount",
        "libmount1",
        "libblkid1",
        "libsmartcols1",
        "liblastlog2-2",
        "bsdutils",
        "login",
        "perl-base",
        "openssl",
        "openssl-provider-legacy",
        "ncurses-bin",
        "libstdc++6",
    }
    assert expected <= set(_purged())


def test_the_purge_fails_closed():
    """A package that survives must stop the build, not ship."""
    assert 'if dpkg -s "$package"' in DOCKERFILE
    assert "survived the purge" in DOCKERFILE
    assert "--force-remove-protected" in DOCKERFILE, "login is protected"


def test_the_patch_status_cannot_claim_a_patch_that_did_not_happen():
    """Plain `apt-get update` exits 0 when every fetch fails, so without this
    flag a build that never reached a mirror wrote "patched"."""
    assert "apt-get update --error-on=any" in DOCKERFILE


def test_the_installer_toolchain_is_still_stripped():
    assert "installer toolchain survived the purge" in DOCKERFILE


def test_the_server_starts_with_the_logging_config():
    cmd = next(line for line in DOCKERFILE.splitlines() if line.startswith("CMD"))
    assert "-c src/gunicorn_conf.py" in cmd
    assert "${PORT:-8080}" in cmd


def test_the_final_image_runs_unprivileged_from_a_flattened_stage():
    final = DOCKERFILE[DOCKERFILE.index("FROM scratch") :]
    assert "COPY --from=prep / /" in final
    assert "USER 10001:10001" in final
