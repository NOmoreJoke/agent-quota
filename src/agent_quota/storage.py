"""SQLite persistence with WAL, file permissions, idempotency and fencing."""

from __future__ import annotations

import contextlib
import os
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from agent_quota.clock import Clock, SystemClock
from agent_quota.errors import FenceConflict, LeaseConflict
from agent_quota.model import (
    AccountScope,
    CapabilityKind,
    CapabilitySnapshot,
    Freshness,
    Health,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS principals (
  principal_id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  label TEXT NOT NULL,
  enabled INTEGER NOT NULL CHECK(enabled IN (0,1))
);
CREATE TABLE IF NOT EXISTS subjects (
  principal_id TEXT NOT NULL REFERENCES principals(principal_id),
  subject_id TEXT NOT NULL,
  label TEXT NOT NULL,
  enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
  PRIMARY KEY(principal_id, subject_id)
);
CREATE TABLE IF NOT EXISTS capabilities (
  principal_id TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  capability_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  unit TEXT NOT NULL,
  enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
  PRIMARY KEY(principal_id, subject_id, capability_id),
  FOREIGN KEY(principal_id, subject_id)
    REFERENCES subjects(principal_id, subject_id)
);
CREATE TABLE IF NOT EXISTS snapshots (
  snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
  principal_id TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  capability_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  unit TEXT NOT NULL,
  used_value INTEGER,
  limit_value INTEGER,
  remaining_value INTEGER,
  reset_at_ns INTEGER,
  observed_at_ns INTEGER NOT NULL,
  freshness TEXT NOT NULL,
  health TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS snapshots_scope_observed
  ON snapshots(principal_id, subject_id, capability_id, observed_at_ns DESC);
CREATE TABLE IF NOT EXISTS refresh_requests (
  idempotency_key TEXT PRIMARY KEY,
  scope_ref TEXT NOT NULL,
  state TEXT NOT NULL,
  fence INTEGER NOT NULL,
  snapshot_id INTEGER,
  error_code TEXT,
  created_at_ns INTEGER NOT NULL,
  updated_at_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS writer_leases (
  lease_name TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  boot_id TEXT NOT NULL,
  expires_mono_ns INTEGER NOT NULL,
  fence INTEGER NOT NULL CHECK(fence > 0)
);
CREATE TABLE IF NOT EXISTS config_journal (
  journal_id TEXT PRIMARY KEY,
  old_digest TEXT NOT NULL,
  new_digest TEXT NOT NULL,
  state TEXT NOT NULL,
  fence INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class Lease:
    name: str
    owner_id: str
    fence: int
    boot_id: str
    expires_mono_ns: int


class Store:
    def __init__(self, path: Path, clock: Clock | None = None) -> None:
        self.path = path
        self.clock = clock or SystemClock()
        self._prepare_path()
        self.connection = sqlite3.connect(path, isolation_level=None, timeout=5)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript(SCHEMA)
        self.connection.execute(
            "INSERT OR IGNORE INTO metadata(key,value) VALUES('schema_version','1')"
        )
        self._enforce_permissions()

    def _prepare_path(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        if not self.path.exists():
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.close(descriptor)
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError("database path must be a regular file")

    def _enforce_permissions(self) -> None:
        os.chmod(self.path, 0o600)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{self.path}{suffix}")
            if sidecar.exists():
                os.chmod(sidecar, 0o600)

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self.connection
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")
            self._enforce_permissions()

    def close(self) -> None:
        self.connection.close()

    def seed_scope(
        self,
        scope: AccountScope,
        *,
        provider: str,
        principal_label: str,
        subject_label: str,
        kind: CapabilityKind,
        unit: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO principals VALUES(?,?,?,1)",
                (scope.principal_id, provider, principal_label),
            )
            connection.execute(
                "INSERT OR REPLACE INTO subjects VALUES(?,?,?,1)",
                (scope.principal_id, scope.subject_id, subject_label),
            )
            connection.execute(
                "INSERT OR REPLACE INTO capabilities VALUES(?,?,?,?,?,1)",
                (
                    scope.principal_id,
                    scope.subject_id,
                    scope.capability_id,
                    kind.value,
                    unit,
                ),
            )

    def authorize(self, scope: AccountScope) -> bool:
        row = self.connection.execute(
            """
            SELECT 1
            FROM capabilities c
            JOIN subjects s
              ON s.principal_id=c.principal_id AND s.subject_id=c.subject_id
            JOIN principals p ON p.principal_id=s.principal_id
            WHERE p.principal_id=? AND s.subject_id=? AND c.capability_id=?
              AND p.enabled=1 AND s.enabled=1 AND c.enabled=1
            """,
            (scope.principal_id, scope.subject_id, scope.capability_id),
        ).fetchone()
        return row is not None

    def acquire_lease(self, name: str, owner_id: str, duration_ns: int) -> Lease:
        if duration_ns <= 0:
            raise ValueError("lease duration must be positive")
        now = self.clock.monotonic_ns()
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM writer_leases WHERE lease_name=?", (name,)
            ).fetchone()
            if row is None:
                fence = 1
            elif (
                row["owner_id"] == owner_id
                or row["boot_id"] != self.clock.boot_id
                or row["expires_mono_ns"] <= now
            ):
                fence = int(row["fence"]) + 1
            else:
                raise LeaseConflict(name)
            expires = now + duration_ns
            if expires > 2**63 - 1:
                raise OverflowError("lease expiry overflow")
            connection.execute(
                """
                INSERT INTO writer_leases VALUES(?,?,?,?,?)
                ON CONFLICT(lease_name) DO UPDATE SET
                  owner_id=excluded.owner_id, boot_id=excluded.boot_id,
                  expires_mono_ns=excluded.expires_mono_ns, fence=excluded.fence
                """,
                (name, owner_id, self.clock.boot_id, expires, fence),
            )
        return Lease(name, owner_id, fence, self.clock.boot_id, expires)

    def assert_fence(
        self,
        lease: Lease,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        active = connection or self.connection
        row = active.execute(
            "SELECT * FROM writer_leases WHERE lease_name=?", (lease.name,)
        ).fetchone()
        if (
            row is None
            or row["owner_id"] != lease.owner_id
            or row["boot_id"] != lease.boot_id
            or row["fence"] != lease.fence
            or row["expires_mono_ns"] <= self.clock.monotonic_ns()
        ):
            raise FenceConflict(lease.name)

    def release_lease(self, lease: Lease) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                DELETE FROM writer_leases
                WHERE lease_name=? AND owner_id=? AND boot_id=? AND fence=?
                """,
                (lease.name, lease.owner_id, lease.boot_id, lease.fence),
            )
            return cursor.rowcount == 1

    @staticmethod
    def _insert_snapshot(
        connection: sqlite3.Connection,
        snapshot: CapabilitySnapshot,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO snapshots(
              principal_id,subject_id,capability_id,kind,unit,used_value,limit_value,
              remaining_value,reset_at_ns,observed_at_ns,freshness,health
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                snapshot.scope.principal_id,
                snapshot.scope.subject_id,
                snapshot.scope.capability_id,
                snapshot.kind.value,
                snapshot.unit,
                snapshot.used,
                snapshot.limit,
                snapshot.remaining,
                snapshot.reset_at_ns,
                snapshot.observed_at_ns,
                snapshot.freshness.value,
                snapshot.health.value,
            ),
        )
        snapshot_id = cursor.lastrowid
        if snapshot_id is None:
            raise RuntimeError("snapshot insert did not return an id")
        return snapshot_id

    def complete_refresh_success(
        self,
        key: str,
        snapshot: CapabilitySnapshot,
        lease: Lease,
    ) -> int:
        with self.transaction() as connection:
            self.assert_fence(lease, connection)
            snapshot_id = self._insert_snapshot(connection, snapshot)
            cursor = connection.execute(
                """
                UPDATE refresh_requests
                SET state='succeeded',snapshot_id=?,error_code=NULL,updated_at_ns=?
                WHERE idempotency_key=? AND scope_ref=? AND fence=? AND state='running'
                """,
                (
                    snapshot_id,
                    self.clock.wall_ns(),
                    key,
                    snapshot.scope.opaque_ref,
                    lease.fence,
                ),
            )
            if cursor.rowcount != 1:
                raise FenceConflict("refresh success transition")
            return snapshot_id

    def latest_snapshot(self, scope: AccountScope) -> CapabilitySnapshot | None:
        row = self.connection.execute(
            """
            SELECT * FROM snapshots
            WHERE principal_id=? AND subject_id=? AND capability_id=?
            ORDER BY observed_at_ns DESC, snapshot_id DESC LIMIT 1
            """,
            (scope.principal_id, scope.subject_id, scope.capability_id),
        ).fetchone()
        return self._snapshot_from_row(row, scope)

    def snapshot_by_id(
        self,
        snapshot_id: int | None,
        scope: AccountScope,
    ) -> CapabilitySnapshot | None:
        if snapshot_id is None:
            return None
        row = self.connection.execute(
            """
            SELECT * FROM snapshots
            WHERE snapshot_id=? AND principal_id=? AND subject_id=? AND capability_id=?
            """,
            (snapshot_id, scope.principal_id, scope.subject_id, scope.capability_id),
        ).fetchone()
        return self._snapshot_from_row(row, scope)

    @staticmethod
    def _snapshot_from_row(
        row: sqlite3.Row | None,
        scope: AccountScope,
    ) -> CapabilitySnapshot | None:
        if row is None:
            return None
        return CapabilitySnapshot(
            scope=scope,
            kind=CapabilityKind(row["kind"]),
            unit=row["unit"],
            used=row["used_value"],
            limit=row["limit_value"],
            remaining=row["remaining_value"],
            reset_at_ns=row["reset_at_ns"],
            observed_at_ns=row["observed_at_ns"],
            freshness=Freshness(row["freshness"]),
            health=Health(row["health"]),
        )

    def refresh_row(self, key: str) -> sqlite3.Row | None:
        row: sqlite3.Row | None = self.connection.execute(
            "SELECT * FROM refresh_requests WHERE idempotency_key=?", (key,)
        ).fetchone()
        return row

    def recover_incomplete_refreshes(self) -> int:
        rows = self.connection.execute(
            "SELECT idempotency_key,scope_ref,fence FROM refresh_requests WHERE state='running'"
        ).fetchall()
        recovered = 0
        with self.transaction() as connection:
            for row in rows:
                lease = connection.execute(
                    "SELECT * FROM writer_leases WHERE lease_name=?",
                    (f"refresh:{row['scope_ref']}",),
                ).fetchone()
                active = (
                    lease is not None
                    and lease["boot_id"] == self.clock.boot_id
                    and lease["fence"] == row["fence"]
                    and lease["expires_mono_ns"] > self.clock.monotonic_ns()
                )
                if active:
                    continue
                connection.execute(
                    """
                    UPDATE refresh_requests
                    SET state='outcome_unknown',error_code='recovered_incomplete',
                        updated_at_ns=?
                    WHERE idempotency_key=? AND state='running'
                    """,
                    (self.clock.wall_ns(), row["idempotency_key"]),
                )
                recovered += 1
        return recovered

    def start_refresh(self, key: str, scope: AccountScope, lease: Lease) -> None:
        now = self.clock.wall_ns()
        with self.transaction() as connection:
            self.assert_fence(lease, connection)
            connection.execute(
                "INSERT INTO refresh_requests VALUES(?,?,?,?,NULL,NULL,?,?)",
                (key, scope.opaque_ref, "running", lease.fence, now, now),
            )

    def finish_refresh(
        self,
        key: str,
        state: str,
        *,
        lease: Lease,
        snapshot_id: int | None = None,
        error_code: str | None = None,
    ) -> None:
        if state not in {"succeeded", "failed", "outcome_unknown"}:
            raise ValueError("invalid refresh terminal state")
        with self.transaction() as connection:
            self.assert_fence(lease, connection)
            cursor = connection.execute(
                """
                UPDATE refresh_requests
                SET state=?,snapshot_id=?,error_code=?,updated_at_ns=?
                WHERE idempotency_key=? AND state='running'
                """,
                (state, snapshot_id, error_code, self.clock.wall_ns(), key),
            )
            if cursor.rowcount != 1:
                raise FenceConflict("refresh terminal transition")

    def list_accounts(self) -> list[dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT p.principal_id,p.provider,p.label AS principal_label,
                   s.subject_id,s.label AS subject_label,c.capability_id,c.kind,c.unit
            FROM principals p
            JOIN subjects s ON s.principal_id=p.principal_id
            JOIN capabilities c
              ON c.principal_id=s.principal_id AND c.subject_id=s.subject_id
            WHERE p.enabled=1 AND s.enabled=1 AND c.enabled=1
            ORDER BY p.principal_id,s.subject_id,c.capability_id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def diagnostic_counts(self) -> dict[str, int]:
        names = ("principals", "subjects", "capabilities", "snapshots", "refresh_requests")
        return {
            name: int(self.connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in names
        }
