# Local Recovery Runbook

This runbook covers the Phase 5 local PostgreSQL backup/restore boundary. It
is intentionally not a cloud deployment or a production backup platform.

## Normal runtime

Start the local runtime with the existing canonical entry point:

```powershell
pwsh -NoProfile -File .\scripts\start-runtime.ps1 -StartEdge
```

The interactive Edge session must already have a normal authenticated Xueqiu
session. The runtime does not accept credentials, copy cookies, or bypass
CAPTCHA. Verify the runtime with:

```powershell
pwsh -NoProfile -File .\scripts\runtime-status.ps1
```

Stop local processes with:

```powershell
pwsh -NoProfile -File .\scripts\stop-runtime.ps1
```

The normal Windows Task Scheduler entry starts the runtime at interactive user
logon. It contains no secret values. If authentication has expired, the
operator must log in normally in the existing Edge profile; historical
intelligence remains readable while the source is unavailable.

## Create a backup

### Scheduler restart and PostgreSQL refresh lock

The canonical refresh uses session advisory lock `4831927501`. The lock now
leases one dedicated PostgreSQL connection for the entire operation, independent
of business Session commits/rollbacks. Release is checked on that same connection;
failure invalidates it and is surfaced as `LOCK_RELEASE`, rather than returning
a contaminated connection to the pool. It needs one additional pool slot per
active refresh. An unexpected server/network disconnect removes a PostgreSQL
session lock; this is detected on cleanup, but this local lock is not a distributed
fencing protocol and cannot guarantee exclusion during an undetected disconnect.

Before restarting a scheduler, confirm the executing task has finished using
run records, logs and connection ownership. Never infer this from `idle` alone,
terminate a database backend or release another session's lock. Normally stop
the verified scheduler, confirm its connections/lock disappear, then restart
the fixed code. To avoid an immediate extra tick, preserve the original next
tick with `--not-before <timezone-qualified ISO timestamp>`. This argument only
delays startup; the existing interval, budgets and ordinary loop stay unchanged.
Do not use it to claim a scheduled refresh has passed before it actually runs.

Ensure the database is reachable. For a consistent operator snapshot, stop
the local backend/scheduler first when a refresh is in progress, then run:

```powershell
pwsh -NoProfile -File .\scripts\backup-database.ps1
```

The command writes a PostgreSQL custom-format dump and a JSON manifest under
`.local/backups`. The manifest contains the Git HEAD, PostgreSQL/migration
metadata, critical row counts, file size, and SHA-256. It does not contain the
`DATABASE_URL` value or any password. `.local/` is Git-ignored.

The backup is database-only. Do not add `.local/edge-cdp-profile`, `.env`, or
runtime logs to a backup bundle. The Edge profile contains authenticated
browser state and must remain under the interactive Windows account boundary.

## Restore into an isolated database

Use a new target name for every drill:

```powershell
pwsh -NoProfile -File .\scripts\restore-database.ps1 `
  -BackupPath .\.local\backups\snowball-<timestamp>.dump `
  -TargetDatabase snowball_restore_verify_<run-id>
```

The script rejects unsafe target names, refuses an existing target before
creation, never calls `dropdb`, and never overwrites the live database. The
restored database is retained for inspection unless an operator explicitly
removes that exact isolated target after the drill.

Restore verification checks:

- Alembic migration head and public table/index/constraint counts;
- critical business row counts from the manifest;
- selected foreign-key integrity and identity uniqueness checks;
- one Asset Product View and one Investor Product View;
- Recent Intelligence Inbox readability;
- persisted Operational Status and latest refresh state.

## Continuation proof

After the isolated restore passes, ensure an authenticated Xueqiu page is
available in the existing CDP Edge context. Run the existing scheduler one-shot
against the isolated database only when a continuation drill is required; keep
credentials in the existing environment rather than putting them on a command
line or in a file. The expected behavior is one normal `SCHEDULED` tick, no
catch-up storm, and reuse of existing RawEvent/Analysis/Opinion/downstream
identities when the source window overlaps the snapshot.

After the drill, restore the normal live environment and verify:

```powershell
pwsh -NoProfile -File .\scripts\start-runtime.ps1 -StartEdge
pwsh -NoProfile -File .\scripts\runtime-status.ps1
```

The final product state should be `HEALTHY` / `FRESH` when the last scheduled
refresh succeeded. Historical failures such as `CDP_UNAVAILABLE` remain
visible and are not deleted.

## Retention and production boundary

P5-2 does not implement automatic retention, encryption at rest, off-host
replication, a secret manager, restore automation on another machine, or a
production database. For any important local artifact, the operator must
apply the host's protected storage and retention policy separately. These are
future production gaps, not reasons to put credentials or browser state into
this repository's backup scripts.
