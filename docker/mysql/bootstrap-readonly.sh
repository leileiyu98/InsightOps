#!/bin/bash
set -euo pipefail

if [[ ! "$MYSQL_DATABASE" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "MYSQL_DATABASE contains unsupported characters" >&2
  exit 1
fi
if [[ ! "$READONLY_DATABASE_USER" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "READONLY_DATABASE_USER contains unsupported characters" >&2
  exit 1
fi
if [[ ! "$READONLY_DATABASE_PASSWORD" =~ ^[A-Za-z0-9_!@#%+=.-]+$ ]]; then
  echo "READONLY_DATABASE_PASSWORD contains unsupported characters" >&2
  exit 1
fi

mysql --host=mysql --user=root --password="$MYSQL_ROOT_PASSWORD" <<SQL
CREATE USER IF NOT EXISTS '${READONLY_DATABASE_USER}'@'%' IDENTIFIED BY '${READONLY_DATABASE_PASSWORD}';
ALTER USER '${READONLY_DATABASE_USER}'@'%' IDENTIFIED BY '${READONLY_DATABASE_PASSWORD}';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM '${READONLY_DATABASE_USER}'@'%';
GRANT SELECT ON \`${MYSQL_DATABASE}\`.* TO '${READONLY_DATABASE_USER}'@'%';
FLUSH PRIVILEGES;
SQL
