#!/usr/bin/env bash
# Wipe Amphetype stats/texts and recreate an empty schema.
# Backs up the current file as jd.db.bak-<timestamp> beside it.
set -euo pipefail

if [ -n "${1:-}" ]; then
  DB="$1"
else
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  if [ -f "$ROOT/amphetype/data/amphetype.ini" ]; then
    # Portable / --local: ini may override db_name
    DB="$(grep -E '^db_name=' "$ROOT/amphetype/data/amphetype.ini" 2>/dev/null | cut -d= -f2- || true)"
  fi
  if [ -z "${DB:-}" ] || [ ! -f "$DB" ]; then
  USER="$(python3 -c "import getpass,re; u=re.sub(r'[^a-z0-9_-]','',getpass.getuser(),flags=re.I) or 'user'; print(u)")"
    LOCAL="$ROOT/amphetype/data/${USER}.db"
    DEFAULT="${HOME}/Library/Application Support/amphetype/${USER}.db"
    if [ -f "$LOCAL" ]; then
      DB="$LOCAL"
    elif [ -f "$DEFAULT" ]; then
      DB="$DEFAULT"
    else
      DB="$DEFAULT"
    fi
  fi
fi

DIR="$(dirname "$DB")"
mkdir -p "$DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
if [ -f "$DB" ]; then
  cp "$DB" "${DB}.bak-${STAMP}"
  echo "Backup: ${DB}.bak-${STAMP}"
  rm "$DB"
fi

python3 - "$DB" <<'PY'
import sqlite3, sys
db = sys.argv[1]
conn = sqlite3.connect(db)
conn.executescript("""
create table source (name text, disabled integer, discount integer);
create table text (id text primary key, source integer, text text, disabled integer);
create table result (w real, text_id text, source integer, wpm real, accuracy real, viscosity real);
create table statistic (w real, data text, type integer, time real, count integer, mistakes integer, viscosity real, source integer);
create table mistake (w real, target text, mistake text, count integer);
create view text_source as
  select id,s.name,text,coalesce(t.disabled,s.disabled)
    from text as t left join source as s on (t.source = s.rowid);
""")
conn.execute("update source set discount = 1 where name = '<Weakspot>' and discount is null")
conn.commit()
conn.close()
print("Fresh database:", db)
PY
