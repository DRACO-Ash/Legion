# syntax=docker/dockerfile:1

# Base image pinned by digest, not by tag. A moving tag means two builds of the
# identical archive can produce different images, different package versions and
# different Container Scan results, with nothing in the repository recording
# which one was scanned. The tag is kept alongside the digest for readability.
#
# python:3.13-slim, resolved 20 November 2026: Python 3.13.18 on Debian 13.7.
# Refreshed from the 9 September digest (3.13.15 on 13.6) because the 0.19.0
# Container Scan named four critical or high interpreter advisories fixed in
# 3.13.16 to 3.13.18. The Debian packages in this digest are the same versions
# the scan flagged, so the refresh does not touch the operating system
# findings; READINESS.md has that account.
# 3.13 rather than 3.12 because the 3.12 line's current patch (3.12.14) carries
# interpreter advisories whose only published fix is on 3.13 or later. The move
# needed no dependency change: requirements-runtime.txt installs unaltered under
# 3.13 with --require-hashes, because the existing hashes already cover the
# cp313 wheels, and the full test suite passes on 3.13.
#
# To refresh: pull the tag, read the digest, change it in both FROM lines below,
# rebuild and re-verify. Never change one of the two.
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS build
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements-runtime.txt .
RUN pip install -r requirements-runtime.txt

FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS prep
# Fail-open OS patch in its own layer, separate from the fail-closed strip below.
# Deliberately fail-open: a blocked or unreachable package mirror must not stop
# the build. But a build where the upgrade silently did nothing used to look
# identical to one where it worked, so the outcome is now recorded two ways: a
# warning on stderr for the build log, and /etc/os-patch-status inside the
# image, which survives the flatten and can be read out of the built artefact.
#
# --error-on=any is what makes that record true. Plain `apt-get update` exits 0
# when every fetch fails, so until 0.19.2 a build that could not even resolve
# the mirror wrote "patched". Measured, 20 November 2026: exit 0 without the
# flag and 100 with it, against an unreachable mirror on apt 3.0.4.
RUN if apt-get update --error-on=any && apt-get -y upgrade; then \
      echo "patched" > /etc/os-patch-status; \
    else \
      echo "unpatched" > /etc/os-patch-status; \
      echo "WARNING: OS patch step failed, base packages ship unpatched" >&2; \
    fi; \
    rm -rf /var/lib/apt/lists/*
RUN useradd -u 10001 -r -s /usr/sbin/nologin appuser

# Purge operating-system packages nothing in the running container uses, the
# same way the installer toolchain is removed below: the files and their dpkg
# records go together, so the scanner's view and the filesystem agree. Ash's
# decision, 20 November 2026, after the 0.19.0 Container Scan.
#
# Chosen by tracing every shared library the interpreter and every compiled
# wheel load inside this exact base image, then keeping anything they reach.
# None of these is reached: util-linux and its libraries, login, perl-base,
# the openssl command-line tool and its legacy provider (Python's ssl module
# uses libssl3t64, which stays), ncurses-bin and libstdc++6. apt and
# libapt-pkg7.0 go too because they cannot run without libstdc++6, and nothing
# needs them after the patch step above.
#
# The packages that carry the 0.19.0 report's critical and high findings and
# ARE reached stay: libc6, libssl3t64 and libgcc-s1. Those need a Debian fix
# or a risk decision, not a purge. READINESS.md has the account.
#
# Fail-closed: if any named package survives, the build stops here. That the
# application still runs without them is proved by the import check below.
RUN set -eu; \
    set -- util-linux mount libmount1 libblkid1 libsmartcols1 liblastlog2-2 \
           bsdutils login perl-base openssl openssl-provider-legacy \
           ncurses-bin libstdc++6 apt libapt-pkg7.0; \
    dpkg --purge --force-remove-essential --force-remove-protected --force-depends "$@"; \
    for package in "$@"; do \
      if dpkg -s "$package" >/dev/null 2>&1; then \
        echo "ERROR: $package survived the purge" >&2; \
        exit 1; \
      fi; \
    done
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app
COPY --chown=10001:10001 src ./src

# Remove the installer toolchain from the runtime image. Nothing the container
# runs needs pip, setuptools or wheel: the virtual environment is fully built by
# the time this stage copies it, and the image is immutable and runs as an
# unprivileged user that could not install into it anyway. Three separate copies
# exist by default and a package scanner catalogues all three: the interpreter's
# own site-packages, the wheel bundled inside ensurepip, and the copy that
# `python -m venv` places in /opt/venv. Deleting them removes the whole class of
# installer-toolchain advisories from the scan surface rather than chasing each
# version, and it removes the ability to pull a package into a running
# container. Fail-closed: if any copy survives, or the application can no longer
# be imported without it, the build stops here rather than shipping.
RUN set -eu; \
    rm -rf /usr/local/lib/python3.*/ensurepip \
           /usr/local/lib/python3.*/site-packages/pip \
           /usr/local/lib/python3.*/site-packages/pip-*.dist-info \
           /opt/venv/lib/python3.*/site-packages/pip \
           /opt/venv/lib/python3.*/site-packages/pip-*.dist-info \
           /opt/venv/lib/python3.*/site-packages/setuptools \
           /opt/venv/lib/python3.*/site-packages/setuptools-*.dist-info \
           /opt/venv/lib/python3.*/site-packages/pkg_resources \
           /opt/venv/lib/python3.*/site-packages/wheel \
           /opt/venv/lib/python3.*/site-packages/wheel-*.dist-info; \
    rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.13 \
          /opt/venv/bin/pip /opt/venv/bin/pip3 /opt/venv/bin/pip3.13 \
          /opt/venv/bin/wheel /opt/venv/bin/wheel3; \
    survivors="$(find / -xdev \( -name 'pip' -o -name 'pip-*.dist-info' \
                 -o -name 'setuptools-*.dist-info' -o -name 'pip-*.whl' \
                 -o -name 'setuptools-*.whl' \) -print)"; \
    if [ -n "$survivors" ]; then \
      echo "ERROR: installer toolchain survived the purge:" >&2; \
      echo "$survivors" >&2; \
      exit 1; \
    fi; \
    python -c "import ssl, fastapi, starlette, uvicorn, gunicorn, httpx, pydantic, pydantic_settings, src.logging_standard"

# Sweep is the LAST filesystem mutation in this stage, after user creation
# and every COPY, since a later instruction can re-introduce a setuid/setgid
# bit. This alone is not sufficient against a scanner that reads layer
# history rather than the final merged view - see the flatten step below.
RUN find / -xdev -perm /6000 \( -type f -o -type d \) -exec chmod a-s {} + 2>/dev/null || true

# Flatten to a single layer with no history. The container-scan policy stops
# on suid_or_guid_set for any bit that ever existed in an earlier layer
# (commonly bundled into the base image itself), even after this stage's own
# chmod sweep - the scan reads per-layer diffs, and an in-place strip can
# still leave a path-less (N/A) finding pointing at a layer that no longer
# exists in the final filesystem view. Copying the entire prep root into a
# scratch stage in one COPY leaves exactly one layer, with only the
# already-stripped permissions ever visible to a layer-history scan.
FROM scratch
COPY --from=prep / /
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app
USER 10001:10001
EXPOSE 8080
# PORT is never set here (platform injects it); default 8080 is honoured in code.
# -c src/gunicorn_conf.py routes gunicorn's and uvicorn's own lines through the
# application's JSON formatter to stdout. Without it they go to stderr in
# gunicorn's text format, which the platform's Logging check rejects.
CMD ["sh","-c","exec gunicorn src.app:app -c src/gunicorn_conf.py -k uvicorn.workers.UvicornWorker -b 0.0.0.0:${PORT:-8080}"]
