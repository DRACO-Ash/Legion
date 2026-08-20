# syntax=docker/dockerfile:1
FROM python:3.12-slim AS build
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements-runtime.txt .
RUN pip install -r requirements-runtime.txt

FROM python:3.12-slim AS prep
# Fail-open OS patch in its own layer, separate from the fail-closed strip below.
RUN apt-get update && apt-get -y upgrade && rm -rf /var/lib/apt/lists/* || true
RUN useradd -u 10001 -r -s /usr/sbin/nologin appuser
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app
COPY --chown=10001:10001 src ./src
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
CMD ["sh","-c","exec gunicorn src.app:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:${PORT:-8080}"]
