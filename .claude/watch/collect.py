#!/usr/bin/env python3
"""Legion Watch collector: the data behind the Legion Watch dashboard.

Drives the vendored App Store MCP server over stdio, reads Legion's health
and pipeline, fingerprints every App Store documentation page and the
platform's own configuration for Legion, compares all of it with the
recorded baseline, and writes the dashboard's data files.

Standard library only. Run with `python3 -I .claude/watch/collect.py OUT_DIR`
from the repository root. Exit 0: collected. Exit 3: the App Store session
is not signed in (the device-code sign-in needs a person). Exit 1: anything
else. A run never prints a document's text or a token.

What counts as a change worth a code review is deliberately narrow: a doc
page whose text changed, a stage or job added or removed, a change to the
service's port, health check, resources or add-ons, a new MCP server build,
or the deployed version falling behind the repository. Each change names the
part of Legion it is likely to touch, as INFERENCE: the page changing proves
only that the page changed.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import pathlib
import queue
import subprocess
import sys
import threading
import urllib.request

APP_ID = "4620cead-c09e-459f-8cdd-5bf79f338908"
ROOT = pathlib.Path(__file__).resolve().parents[2]
WATCH = ROOT / ".claude" / "watch"
BASELINE = WATCH / "baseline.json"
CHANGELOG = WATCH / "changes.json"
BUNDLE = ROOT / ".claude" / "mcp" / "appstore-mcp.mjs"
APPSTORE = "https://appstore.bluestaq.com"
TIMEOUT = 90

# Which part of Legion each App Store page governs. A change to a page with
# no entry here is still reported, as "not known to affect Legion".
GOVERNS = {
    "pipeline/logging": "src/logging_standard.py, src/gunicorn_conf.py",
    "pipeline/code-quality": "docs/SONAR-RULE-REGISTER.md, tests/test_sonar_*.py",
    "pipeline/dast": "start-up without credentials, /healthz",
    "pipeline/tests": "requirements.txt, the test stage",
    "pipeline/templates": "Dockerfile, package layout",
    "pipeline/overview": "the stage list CLAUDE.md and package.sh assume",
    "pipeline/multi-language": "package layout",
    "pipeline/deploy": "PORT, health check path, Dockerfile CMD",
    "submitting/package-requirements": "scripts/package.sh, .gitattributes",
    "submitting/overview": "the release procedure",
    "submitting/upload-wizard": "the release procedure",
    "auth/headers": "X-Auth-Request-Email logging, the no-authentication decision",
    "auth/roles": "the no-authentication decision",
    "managing/env-vars": "UDL_USERNAME, UDL_PASSWORD, LOG_LEVEL",
    "addons/file-storage": "STORAGE_MOUNT_PATH and src/store.py",
    "troubleshooting/pitfalls": "general",
    "troubleshooting/pipeline-failures": "general",
    "troubleshooting/deploy-failures": "general",
    "mcp/install": ".claude/mcp bundle, .mcp.json",
    "mcp/authentication": ".claude/mcp bundle, .mcp.json",
    "mcp/tools-reference": "Legion Watch collector",
}


class SignInNeeded(Exception):
    pass


class Mcp:
    """A minimal MCP stdio client: one request at a time, by id."""

    def __init__(self) -> None:
        env = dict(os.environ)
        env.update(
            APPSTORE_URL=APPSTORE,
            APPSTORE_MCP_NO_SELF_UPDATE="1",
            NODE_USE_ENV_PROXY="1",
        )
        self.proc = subprocess.Popen(
            ["node", str(BUNDLE)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            text=True,
        )
        self.lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self.next_id = 0
        self._request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "legion-watch", "version": "1"},
            },
        )
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _pump(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.lines.put(line)

    def _send(self, message: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def _request(self, method: str, params: dict) -> dict:
        self.next_id += 1
        wanted = self.next_id
        self._send({"jsonrpc": "2.0", "id": wanted, "method": method, "params": params})
        while True:
            message = json.loads(self.lines.get(timeout=TIMEOUT))
            if message.get("id") == wanted:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error'].get('message')}")
                return message["result"]

    def tool(self, name: str, **arguments: object) -> object:
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        text = "".join(c.get("text", "") for c in result.get("content", []))
        if result.get("isError"):
            if "Authentication required" in text or "login" in text.lower():
                raise SignInNeeded(name)
            raise RuntimeError(f"{name} failed: {text[:200]}")
        if "Authentication required" in text:
            raise SignInNeeded(name)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def close(self) -> None:
        self.proc.terminate()


def sha(text: str | bytes) -> str:
    data = text.encode() if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()


def endpoint(mcp: Mcp, path: str) -> dict:
    answer = mcp.tool("call_app_endpoint", appId=APP_ID, path=path)
    if not isinstance(answer, dict) or answer.get("status") != 200:
        return {}
    return json.loads(answer["body"])


def stage_results(events: list[dict], stages: list[dict]) -> list[dict]:
    """Each expected stage's latest outcome, from the platform's event log."""
    rows = []
    for order, stage in enumerate(stages, 1):
        key = stage["key"]
        outcomes = [
            e
            for e in events
            if e["eventType"].startswith(key + "_")
            and not e["eventType"].endswith("_started")
            and e["eventType"][len(key) + 1 :] in {"passed", "failed", "warning", "warnings", "skipped"}
        ]
        latest = max(outcomes, key=lambda e: e["createdAt"], default=None)
        result = latest["eventType"][len(key) + 1 :] if latest else "not reported"
        rows.append(
            {
                "order": order,
                "stage": stage["label"],
                "result": "warnings" if result == "warning" else result,
                "at": latest["createdAt"][:19].replace("T", " ") if latest else "",
            }
        )
    return rows


def published_mcp_sha() -> str:
    with urllib.request.urlopen(f"{APPSTORE}/api/mcp/version", timeout=20) as reply:  # noqa: S310
        return json.loads(reply.read()).get("sha256", "")


def collect() -> dict:
    mcp = Mcp()
    try:
        diag = mcp.tool("get_pipeline_diagnosis", appId=APP_ID)
        details = mcp.tool("get_app_details", appId=APP_ID)
        ready = endpoint(mcp, "/readyz")
        tree = mcp.tool("list_docs")
        docs = {}
        for section in tree["sections"]:
            for page in section["pages"]:
                body = mcp.tool("read_doc", slug=page["slug"])
                text = body.get("markdown", "") if isinstance(body, dict) else str(body)
                docs[page["slug"]] = {
                    "section": section["title"],
                    "title": page["title"],
                    "sha": sha(text),
                    "chars": len(text),
                }
    finally:
        mcp.close()
    service = details["services"][0]
    return {
        "diag": diag,
        "details": details,
        "ready": ready,
        "docs": docs,
        "config": {
            "stages": [s["key"] for s in details.get("expectedStages", [])],
            "deploy_stages": [s["key"] for s in details.get("deployStages", [])],
            "jobs": sorted(j["name"] for j in diag["pipeline"]["jobs"]),
            "blocking_jobs": sorted(
                j["name"] for j in diag["pipeline"]["jobs"] if not j["allowFailure"]
            ),
            "service": {
                k: service.get(k)
                for k in ("containerPort", "healthCheckPath", "resourceMemory", "resourceCpu")
            },
            "addons": sorted(
                f"{a['addonType']}:{json.dumps(a.get('connectionVars') or {}, sort_keys=True)}"
                for a in details.get("addons", [])
                if a.get("enabled")
            ),
            "mcp_published": published_mcp_sha(),
            "mcp_vendored": sha(BUNDLE.read_bytes()),
        },
    }


def compare(now: dict, base: dict | None, stamp: str) -> list[dict]:
    if base is None:
        return [
            {
                "at": stamp,
                "kind": "Baseline",
                "item": "Everything",
                "detail": f"First reading: {len(now['docs'])} documentation pages, "
                f"{len(now['config']['stages'])} stages, {len(now['config']['jobs'])} jobs.",
                "affects": "Nothing. Later readings are compared with this one.",
            }
        ]
    changes = []

    def note(kind: str, item: str, detail: str, affects: str) -> None:
        changes.append(
            {"at": stamp, "kind": kind, "item": item, "detail": detail, "affects": affects}
        )

    for slug, page in now["docs"].items():
        old = base["docs"].get(slug)
        where = GOVERNS.get(slug, "not known to affect Legion")
        if old is None:
            note("Doc added", page["title"], f"New page {slug}.", where)
        elif old["sha"] != page["sha"]:
            note(
                "Doc changed",
                page["title"],
                f"{slug}: {old['chars']} to {page['chars']} characters.",
                where,
            )
    for slug in base["docs"].keys() - now["docs"].keys():
        note("Doc removed", base["docs"][slug]["title"], f"{slug} is gone.", GOVERNS.get(slug, "general"))

    for key, label, affects in (
        ("stages", "Pipeline stage", "CLAUDE.md, scripts/check-quality-gate.sh"),
        ("deploy_stages", "Deploy stage", "the release procedure"),
        ("jobs", "Pipeline job", "the local gate may not mirror it"),
        ("blocking_jobs", "Blocking job", "a gate that used to be advisory now blocks, or the reverse"),
    ):
        before, after = set(base["config"][key]), set(now["config"][key])
        for item in sorted(after - before):
            note(f"{label} added", item, f"{item} appeared.", affects)
        for item in sorted(before - after):
            note(f"{label} removed", item, f"{item} is gone.", affects)
    for field, value in now["config"]["service"].items():
        if base["config"]["service"].get(field) != value:
            note(
                "Service setting",
                field,
                f"{base['config']['service'].get(field)} to {value}.",
                "Dockerfile, src/main.py, src/routes/health.py",
            )
    if base["config"]["addons"] != now["config"]["addons"]:
        note("Add-ons", "Add-on set", "Enabled add-ons or their variables changed.", "src/store.py, STORAGE_MOUNT_PATH")
    if base["config"]["mcp_published"] != now["config"]["mcp_published"]:
        note("MCP server", "New build published", "The App Store published a new MCP server.", "commit the new bundle to .claude/mcp")
    return changes


def write_csv(path: pathlib.Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def health_rows(now: dict, repo_version: str, stamp: str) -> list[dict]:
    diag, details, ready, config = now["diag"], now["details"], now["ready"], now["config"]
    live = ready.get("version", "unreachable")
    attention = len(details.get("checksNeedingAttention") or [])
    uptime = ready.get("uptime_seconds")

    def row(check: str, value: object, state: str, note: str) -> dict:
        return {"check": check, "value": value, "state": state, "note": note}

    return [
        row("Readiness", ready.get("status", "unreachable"), "ok" if ready.get("status") == "ok" else "bad", "GET /readyz on the deployed app"),
        row("Platform diagnosis", diag["troubleshooting"]["status"], "ok" if diag["troubleshooting"]["status"] == "HEALTHY" else "bad", diag["troubleshooting"]["summary"]),
        row("App state", details.get("state"), "ok" if details.get("state") == "APPROVED" else "warn", "App Store approval state"),
        row("Live version", live, "ok" if live == repo_version else "warn", f"Repository is at {repo_version}"),
        row("OS patch status", ready.get("os_patch_status", "unknown"), "ok" if ready.get("os_patch_status") == "patched" else "bad", "Recorded by the image build"),
        row("Storage writable", ready.get("storage_writable"), "ok" if ready.get("storage_writable") else "bad", "File-storage add-on at /data"),
        row("UDL credentials", ready.get("udl_configured"), "ok" if ready.get("udl_configured") else "bad", "Set in the platform's environment variables"),
        row("Uptime (hours)", round(uptime / 3600, 1) if uptime else "", "ok", "Since the last start"),
        row("Pipeline", diag["pipeline"]["status"], "ok" if diag["pipeline"]["status"] == "success" else "bad", f"Pipeline {diag['pipeline']['pipelineId']}"),
        row("cATO score", details.get("catoScore"), "ok" if details.get("catoScore") == 100 else "warn", "As the App Store reports it"),
        row("Checks needing attention", attention, "ok" if attention == 0 else "warn", "Advisory findings the platform flags"),
        row("MCP server build", "current" if config["mcp_published"] == config["mcp_vendored"] else "behind", "ok" if config["mcp_published"] == config["mcp_vendored"] else "warn", "Vendored bundle against the App Store's published build"),
        row("Last reading", stamp, "ok", "When this collector last ran"),
    ]


def main() -> int:
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "watch-out")
    out.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    try:
        now = collect()
    except SignInNeeded:
        print("SIGN-IN NEEDED: the App Store session is not signed in.", file=sys.stderr)
        return 3
    base = json.loads(BASELINE.read_text()) if BASELINE.exists() else None
    changes = compare(now, base, stamp)
    log = json.loads(CHANGELOG.read_text()) if CHANGELOG.exists() else []
    log = changes + log
    repo_version = (ROOT / "src" / "VERSION").read_text().strip()

    write_csv(out / "health.csv", health_rows(now, repo_version, stamp), ["check", "value", "state", "note"])
    write_csv(out / "stages.csv", stage_results(now["details"].get("pipelineEvents", []), now["details"].get("expectedStages", []) + now["details"].get("deployStages", [])), ["order", "stage", "result", "at"])
    write_csv(
        out / "jobs.csv",
        [
            {"job": j["name"], "stage": j["stage"], "status": j["status"], "blocking": "yes" if not j["allowFailure"] else "no", "seconds": j.get("durationSeconds")}
            for j in now["diag"]["pipeline"]["jobs"]
        ],
        ["job", "stage", "status", "blocking", "seconds"],
    )
    changed = {c["detail"].split(":")[0] for c in changes if c["kind"] == "Doc changed"}
    write_csv(
        out / "docs.csv",
        [
            {
                "section": p["section"],
                "page": p["title"],
                "slug": slug,
                "characters": p["chars"],
                "fingerprint": p["sha"][:12],
                "state": "changed" if slug in changed else ("new" if base and slug not in base["docs"] else "unchanged"),
                "governs": GOVERNS.get(slug, "not used by Legion"),
            }
            for slug, p in now["docs"].items()
        ],
        ["section", "page", "slug", "characters", "fingerprint", "state", "governs"],
    )
    write_csv(out / "changes.csv", log, ["at", "kind", "item", "detail", "affects"])

    WATCH.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps({"docs": now["docs"], "config": now["config"]}, indent=1, sort_keys=True) + "\n")
    CHANGELOG.write_text(json.dumps(log, indent=1) + "\n")
    real = [c for c in changes if c["kind"] != "Baseline"]
    print(json.dumps({"at": stamp, "changes": len(real), "kinds": sorted({c["kind"] for c in real})}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # report the cause, never a token or a document
        print(f"FAILED: {type(error).__name__}: {str(error)[:300]}", file=sys.stderr)
        sys.exit(1)
