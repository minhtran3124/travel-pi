#!/bin/sh
# Backup / restore the Supabase Postgres database with pg_dump / pg_restore.
# Runbook: docs/supabase-backup.md
#
# Usage:
#   BACKUP_DB_URL=<session-pooler-uri> backup_db.sh backup  [--dry-run]
#   RESTORE_DB_URL=<scratch-db-uri>    backup_db.sh restore <file.dump> [--dry-run]
#
# BACKUP_DB_URL   Supabase SESSION POOLER connection string (port 5432). The direct
#                 host is IPv6-only on the Free plan; the transaction pooler (6543)
#                 breaks pg_dump. Never commit it.
# RESTORE_DB_URL  A SCRATCH database. Never point it at production.
# BACKUP_DIR      Where dumps are written (default: $HOME/travel-pi-backups).
#                 Must be OUTSIDE this repository; dumps hold user data.
# --dry-run       Print the command with the password masked; no connection.
set -eu

die() { echo "error: $*" >&2; exit 1; }

# Mask the password in a postgres URI: scheme://user:SECRET@host -> scheme://user:****@host
mask() { printf '%s' "$1" | sed 's#\(://[^:/@]*\):[^@]*@#\1:****@#'; }

usage() { sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-2}"; }

cmd="${1:-}"
[ -n "$cmd" ] || usage
shift

dry=0
file=""
for a in "$@"; do
  case "$a" in
    --dry-run) dry=1 ;;
    -h|--help) usage 0 ;;
    -*) die "unknown option: $a" ;;
    *) file="$a" ;;
  esac
done

# Resolve BACKUP_DIR to an absolute path and refuse any location inside the repo.
dir="${BACKUP_DIR:-$HOME/travel-pi-backups}"
case "$dir" in /*) ;; *) dir="$(pwd)/$dir" ;; esac
script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(git -C "$script_dir" rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "$repo_root" ]; then
  case "$dir/" in
    "$repo_root"/*) die "BACKUP_DIR ($dir) is inside the repository ($repo_root); use a path outside it" ;;
  esac
fi

case "$cmd" in
  backup)
    [ -n "${BACKUP_DB_URL:-}" ] || die "BACKUP_DB_URL is not set (Supabase session pooler URI, port 5432)"
    out="$dir/travel-pi-$(date -u +%Y%m%dT%H%M%SZ).dump"
    if [ "$dry" -eq 1 ]; then
      echo "[dry-run] mkdir -p $dir"
      echo "[dry-run] PGDATABASE=$(mask "$BACKUP_DB_URL") pg_dump --format=custom --no-owner --no-privileges --file=$out"
      exit 0
    fi
    command -v pg_dump >/dev/null || die "pg_dump not found; install the postgresql client (major version >= server)"
    mkdir -p "$dir"
    chmod 700 "$dir"
    # The URI goes through PGDATABASE so the password never shows in the process list.
    PGDATABASE="$BACKUP_DB_URL" pg_dump --format=custom --no-owner --no-privileges --file="$out"
    chmod 600 "$out"
    echo "wrote $out"
    ;;
  restore)
    [ -n "$file" ] || die "restore needs a dump file: backup_db.sh restore <file.dump>"
    [ -n "${RESTORE_DB_URL:-}" ] || die "RESTORE_DB_URL is not set (point it at a SCRATCH database)"
    if [ -n "${BACKUP_DB_URL:-}" ] && [ "$BACKUP_DB_URL" = "$RESTORE_DB_URL" ]; then
      die "RESTORE_DB_URL equals BACKUP_DB_URL; restore into a scratch database, never the source"
    fi
    if [ "$dry" -eq 1 ]; then
      echo "[dry-run] PGDATABASE=$(mask "$RESTORE_DB_URL") pg_restore --no-owner --no-privileges --exit-on-error $file"
      exit 0
    fi
    [ -f "$file" ] || die "dump file not found: $file"
    command -v pg_restore >/dev/null || die "pg_restore not found; install the postgresql client"
    PGDATABASE="$RESTORE_DB_URL" pg_restore --no-owner --no-privileges --exit-on-error "$file"
    echo "restored $file"
    ;;
  *) usage ;;
esac
