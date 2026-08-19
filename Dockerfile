# syntax=docker/dockerfile:1
FROM python:3.12-slim AS build
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements-runtime.txt .
RUN pip install -r requirements-runtime.txt

FROM python:3.12-slim
# Fail-open OS patch in its own layer, separate from the fail-closed strip below.
RUN apt-get update && apt-get -y upgrade && rm -rf /var/lib/apt/lists/* || true
RUN useradd -u 10001 -r -s /usr/sbin/nologin appuser
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app
COPY --chown=10001:10001 src ./src
# Sweep is the LAST mutation before USER, after user creation and every COPY,
# since a later instruction can re-introduce a setuid/setgid bit.
RUN find / -xdev -perm /6000 \( -type f -o -type d \) -exec chmod a-s {} + 2>/dev/null || true
USER 10001:10001
EXPOSE 8080
# PORT is never set here (platform injects it); default 8080 is honoured in code.
CMD ["sh","-c","exec gunicorn src.app:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:${PORT:-8080}"]
