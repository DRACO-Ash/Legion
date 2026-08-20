"""Atomic JSON store for the tracked-systems catalogue.

Default per data-layer: an atomic JSON store on the file-storage add-on
(STORAGE_MOUNT_PATH), not a database - this catalogue is single-writer,
low-concurrency (a handful of analysts adding entries), with no relational
queries. Move to Postgres only if that changes.

- Write path is temp-write then rename, so a crash never leaves a half
  written file.
- Records are archived, not deleted, so a lifecycle-ended entry stays
  auditable rather than vanishing.
- Updates are anti-shrink merges: a partial payload never clears a field
  it didn't send.
- The store is versioned (schema_version) so a future shape change ships
  a forward, idempotent migration rather than breaking old snapshots.
- Path is resolved at call time, not at import/construction, since an
  add-on mount can be empty at process boot.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_LOGGER_NAME = "udl_tactics_app"
AUDIT_LOGGER_NAME = f"{APP_LOGGER_NAME}.audit"

logger = logging.getLogger(f"{APP_LOGGER_NAME}.store")
audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)

SCHEMA_VERSION = 1
STORE_FILENAME = "tracked_systems.json"
BACKUP_DIR = "backups"
MAX_BACKUPS = 10


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _resolve_data_dir() -> Path:
    """Read the mount path at call time (App Store file-storage add-on),
    falling back to a local ./data directory for local dev."""
    mount = os.environ.get("STORAGE_MOUNT_PATH", "").strip()
    base = Path(mount) if mount else Path.cwd() / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _sanitize_actor(actor: str, max_len: int = 64) -> str:
    """Strip non-printable characters (defends against log injection via a
    forged newline/control sequence) and bound the length."""
    cleaned = "".join(ch for ch in actor if ch.isprintable())
    return cleaned[:max_len]


def _emit_audit(event: str, actor: str, **fields: Any) -> None:
    """One structured JSON line per privileged action: actor, timestamp, and
    whatever before/after detail the caller has. Never includes a secret -
    callers only ever pass catalogue-level fields (ids, names, which fields
    changed), never credentials."""
    record = {
        "event": event,
        "actor": _sanitize_actor(actor),
        "timestamp": _now_iso(),
        **fields,
    }
    audit_logger.info(json.dumps(record, default=str))


class StoreValidationError(Exception):
    """Raised when a record fails boundary validation before being written."""


class TrackedSystemsStore:
    def __init__(self, seed_records: list[dict[str, Any]] | None = None):
        self._seed_records = seed_records or []

    def _store_path(self) -> Path:
        return _resolve_data_dir() / STORE_FILENAME

    def _read_raw(self) -> dict[str, Any]:
        path = self._store_path()
        if not path.exists():
            return self._seed()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Store file unreadable, treating as absent: %s", exc)
            return self._seed()
        return self._migrate(data)

    def _migrate(self, data: dict[str, Any]) -> dict[str, Any]:
        """Forward, additive, idempotent migration. Never drops unknown fields."""
        version = data.get("schema_version", 0)
        if version < 1:
            data.setdefault("systems", {})
            data["schema_version"] = 1
        return data

    def _seed(self) -> dict[str, Any]:
        """Idempotent: only creates the store if genuinely absent. Re-running
        against an existing store never re-seeds over live edits."""
        systems: dict[str, Any] = {}
        now = _now_iso()
        for record in self._seed_records:
            record_id = str(uuid.uuid4())
            systems[record_id] = {
                **record,
                "id": record_id,
                "archived": False,
                "created_at": now,
                "updated_at": now,
            }
        data = {"schema_version": SCHEMA_VERSION, "systems": systems}
        self._write_atomic(data)
        logger.info("Seeded tracked-systems store with %d records", len(systems))
        return data

    def _write_atomic(self, data: dict[str, Any]) -> None:
        path = self._store_path()
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)  # atomic on the same filesystem

    def _backup(self) -> None:
        """Timestamped copy before a destructive action (archive), pruned to
        the newest MAX_BACKUPS so storage doesn't grow without limit."""
        path = self._store_path()
        if not path.exists():
            return
        backup_dir = path.parent / BACKUP_DIR
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        backup_path = backup_dir / f"{STORE_FILENAME}.{stamp}.bak"
        backup_path.write_bytes(path.read_bytes())
        logger.info("Backed up store to %s", backup_path.name)

        backups = sorted(backup_dir.glob(f"{STORE_FILENAME}.*.bak"))
        for stale in backups[:-MAX_BACKUPS]:
            stale.unlink(missing_ok=True)

    def probe_writable(self) -> tuple[bool, str]:
        """Prove the data directory is actually writable with a real write,
        never an existence check - `mkdir` on an existing directory succeeds
        without write permission, so a root-owned or read-only mount would
        pass an existence check and only fail on the first real write (the
        App Store's non-root container against a root-owned volume add-on
        returns EACCES until securityContext.fsGroup is set - see
        appstore-gate-compliance's failure catalogue). Returns (True, "") on
        success or (False, "<errno/message>") on failure; the caller decides
        what to do with that detail."""
        try:
            data_dir = _resolve_data_dir()
            probe_path = data_dir / ".readyz-probe"
            probe_path.write_text("ok", encoding="utf-8")
            probe_path.unlink()
            return True, ""
        except OSError as exc:
            return False, f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list(
        self,
        *,
        nation: str | None = None,
        regime: str | None = None,
        status: str | None = None,
        q: str | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        data = self._read_raw()
        records = list(data["systems"].values())

        if not include_archived:
            records = [r for r in records if not r.get("archived")]
        if nation:
            records = [
                r
                for r in records
                if r.get("nation", "").casefold() == nation.casefold()
            ]
        if regime:
            records = [
                r
                for r in records
                if r.get("regime", "").casefold() == regime.casefold()
            ]
        if status:
            records = [r for r in records if r.get("status") == status]
        if q:
            needle = q.strip().casefold()
            records = [
                r for r in records if needle in json.dumps(r, default=str).casefold()
            ]
        records.sort(
            key=lambda r: (r.get("launch_year") or 0, r.get("catalogue_name") or "")
        )
        return records

    def get(self, record_id: str) -> dict[str, Any] | None:
        data = self._read_raw()
        return data["systems"].get(record_id)

    def create(self, record: dict[str, Any], actor: str = "unknown") -> dict[str, Any]:
        data = self._read_raw()
        record_id = str(uuid.uuid4())
        now = _now_iso()
        stored = {
            **record,
            "id": record_id,
            "archived": False,
            "created_at": now,
            "updated_at": now,
        }
        data["systems"][record_id] = stored
        self._write_atomic(data)
        _emit_audit(
            "system_created",
            actor,
            record_id=record_id,
            catalogue_name=stored.get("catalogue_name"),
        )
        return stored

    def update(
        self, record_id: str, patch: dict[str, Any], actor: str = "unknown"
    ) -> dict[str, Any] | None:
        """Anti-shrink merge: only overwrite keys present in `patch`; every
        field the caller didn't send survives untouched."""
        data = self._read_raw()
        existing = data["systems"].get(record_id)
        if existing is None:
            return None
        merged = {**existing, **patch}
        merged["id"] = record_id
        merged["updated_at"] = _now_iso()
        data["systems"][record_id] = merged
        self._write_atomic(data)
        _emit_audit(
            "system_updated",
            actor,
            record_id=record_id,
            fields_changed=sorted(patch.keys()),
        )
        return merged

    def archive(self, record_id: str, actor: str = "unknown") -> dict[str, Any] | None:
        data = self._read_raw()
        existing = data["systems"].get(record_id)
        if existing is None:
            return None
        self._backup()
        existing["archived"] = True
        existing["updated_at"] = _now_iso()
        data["systems"][record_id] = existing
        self._write_atomic(data)
        _emit_audit(
            "system_archived",
            actor,
            record_id=record_id,
            catalogue_name=existing.get("catalogue_name"),
        )
        return existing
