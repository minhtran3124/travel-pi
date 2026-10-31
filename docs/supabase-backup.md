# Supabase backup and restore

The Supabase Free plan has no automatic backups and no point-in-time recovery. A paused or deleted
project can lose its data. This runbook gives a manual logical backup with `pg_dump`, and a restore
check into a scratch database. The script is `apps/api/scripts/backup_db.sh`.

> **Status: SKIPPED (live run).** The script and this runbook are written and the dry run is
> verified. The live dump and the live restore were not run: they need the real Supabase project
> and the live Render deploy (#337). Run the drill below once before relying on it.

## Prerequisites

- A PostgreSQL client with `pg_dump` and `pg_restore`. Its major version must be equal to or newer
  than the Supabase server version.
- A **backup location outside the repository**, for example `~/travel-pi-backups`. Dumps contain
  user data. The script refuses a `BACKUP_DIR` inside the repo, and `.gitignore` excludes `*.dump`
  as a second guard. Keep the folder private (the script sets mode 700 on a folder it creates, and 600 on each dump).
- The script passes the database URI to `pg_dump` with `--dbname`, so the password is visible in
  `ps` to other users of the same machine while it runs. Run it on a machine only you use.

## Connection string: use the session pooler (port 5432)

In the Supabase dashboard: **Connect** > **Session pooler**. Copy the URI.

| Mode | Port | Use for backup |
|------|------|----------------|
| Direct connection | 5432 (`db.<ref>.supabase.co`) | No. It is **IPv6 only** on the Free plan; many networks cannot reach it. |
| Session pooler | **5432** (`aws-0-<region>.pooler.supabase.com`, user `postgres.<ref>`) | **Yes.** IPv4 works and the session is stable for `pg_dump`. |
| Transaction pooler | 6543 | No. It breaks `pg_dump` (prepared statements, session state). |

Never commit the URI or paste it into logs. Export it only in your shell:

```bash
export BACKUP_DB_URL='postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres'
```

## Back up

```bash
# Check first: prints the command with the password masked, no connection
apps/api/scripts/backup_db.sh backup --dry-run

# Real dump to $BACKUP_DIR (default ~/travel-pi-backups), custom format, timestamped
BACKUP_DIR=~/travel-pi-backups apps/api/scripts/backup_db.sh backup
```

Run it on a schedule you can keep (weekly at least, and before every migration or deploy that
changes the schema). Copy the dump to a second private location (encrypted drive or private
bucket). A backup on the same laptop is not a backup.

## Restore into a scratch database

Always restore into a **scratch database**, never over production. Create one locally or in a
throwaway Postgres (it must have the `vector` extension, as the app uses pgvector):

```bash
# Use the same Postgres major version as the Supabase project (new projects run 17):
# pg_restore cannot read a dump made by a newer pg_dump.
docker run -d --name scratch-pg -e POSTGRES_PASSWORD=scratch -p 55432:5432 pgvector/pgvector:pg17
export RESTORE_DB_URL='postgresql://postgres:scratch@localhost:55432/postgres'

# Supabase keeps the vector type in an `extensions` schema that pg_dump does not recreate:
psql "$RESTORE_DB_URL" -c 'create schema if not exists extensions; create extension if not exists vector with schema extensions;'

apps/api/scripts/backup_db.sh restore ~/travel-pi-backups/<file>.dump --dry-run
apps/api/scripts/backup_db.sh restore ~/travel-pi-backups/<file>.dump
```

`pg_restore` may still print errors about Supabase-only roles or schemas. The restore keeps going
past them, so judge it by the data, not by the exit message: compare row counts of key tables (`trips`, `bookings`, `expenses`) against
the source, and check `alembic_version` matches the deployed migration head. Then remove the
scratch database (`docker rm -f scratch-pg`).

## Recovering a real incident

1. **Project paused** (Free plan pauses after inactivity): in the dashboard, unpause / restore
   project. Data is kept for a limited window after a pause; after that it may be gone, which is
   why the dump matters.
2. **Data lost or corrupted**: create or unpause a project, restore the latest dump into it with
   the same script (set `RESTORE_DB_URL` to the new project's session pooler URI), run
   `alembic upgrade head` from `apps/api/`, then point `DATABASE_URL` (and Supabase settings) at it.
   The script blocks a restore into the same host and database as `BACKUP_DB_URL` (a best-effort check: the same
   database behind another pooler or host is not detected); unset `BACKUP_DB_URL` for a
   deliberate recovery into a fresh project.

## Drill checklist (not yet run: SKIPPED)

- [ ] Live `backup` against the Supabase session pooler produces a non-empty `.dump`.
- [ ] `restore` into a scratch database finishes without error.
- [ ] Row counts and `alembic_version` match the source.
- [ ] Dump copied to a second private location; no dump or URI is in git.
