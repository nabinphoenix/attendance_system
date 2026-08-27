#!/bin/bash
set -euo pipefail

# Platform hooks receive Elastic Beanstalk environment properties. Neither value
# is bundled with the application version or written to a temporary file.
: "${DATABASE_URL:?DATABASE_URL must be configured as an Elastic Beanstalk environment property.}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be configured as an Elastic Beanstalk environment property.}"

case "${DATABASE_URL}" in
  postgresql://antimbench_app:*@127.0.0.1:5432/antimbench|postgresql://antimbench_app:*@127.0.0.1:5432/antimbench\?*)
    ;;
  *)
    echo "DATABASE_URL must target the local antimbench database with the antimbench_app role." >&2
    exit 1
    ;;
esac

PGDATA="/var/lib/pgsql/data"
PG_CONF="${PGDATA}/postgresql.conf"
PG_HBA="${PGDATA}/pg_hba.conf"
PG_SERVICE="postgresql"

set_postgresql_setting() {
  local setting="$1"
  local value="$2"

  if grep -Eq "^[[:space:]]*#?[[:space:]]*${setting}[[:space:]]*=" "${PG_CONF}"; then
    sed -ri "s|^[[:space:]]*#?[[:space:]]*${setting}[[:space:]]*=.*$|${setting} = ${value}|" "${PG_CONF}"
  else
    printf '\n%s = %s\n' "${setting}" "${value}" >>"${PG_CONF}"
  fi
}

configure_loopback_authentication() {
  local updated_hba
  updated_hba="$(mktemp "${PG_HBA}.XXXXXX")"

  awk '
    BEGIN { OFS="\t" }
    /^[[:space:]]*#/ || /^[[:space:]]*$/ { print; next }
    $1 == "host" && $4 == "127.0.0.1/32" {
      $5 = "scram-sha-256"; found_ipv4 = 1
    }
    $1 == "host" && $4 == "::1/128" {
      $5 = "scram-sha-256"; found_ipv6 = 1
    }
    { print }
    END { if (!found_ipv4 || !found_ipv6) exit 2 }
  ' "${PG_HBA}" >"${updated_hba}"

  install -o postgres -g postgres -m 0600 "${updated_hba}" "${PG_HBA}"
  rm -f "${updated_hba}"
}

if [[ ! -s "${PGDATA}/PG_VERSION" ]]; then
  postgresql-setup --initdb --unit "${PG_SERVICE}"
fi

if [[ ! -f "${PG_CONF}" || ! -f "${PG_HBA}" ]]; then
  echo "PostgreSQL initialization did not create the expected configuration files." >&2
  exit 1
fi

# PostgreSQL never binds to a public interface in this single-instance demo.
set_postgresql_setting "listen_addresses" "'127.0.0.1'"
set_postgresql_setting "password_encryption" "'scram-sha-256'"
configure_loopback_authentication

systemctl enable "${PG_SERVICE}"
systemctl restart "${PG_SERVICE}"

postgres_ready=false
for attempt in {1..15}; do
  if runuser -u postgres -- pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
    postgres_ready=true
    break
  fi
  sleep 2
done

if [[ "${postgres_ready}" != "true" ]]; then
  echo "PostgreSQL did not become ready on 127.0.0.1:5432." >&2
  exit 1
fi

# psql expands :'password' as a correctly SQL-quoted literal. The password is
# never interpolated into SQL or written to disk.
runuser -u postgres -- psql --dbname=postgres -v ON_ERROR_STOP=1 --set=password="${POSTGRES_PASSWORD}" <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'antimbench_app') THEN
    CREATE ROLE antimbench_app LOGIN;
  END IF;
END
$$;
ALTER ROLE antimbench_app WITH LOGIN PASSWORD :'password';
SQL

if ! runuser -u postgres -- psql --dbname=postgres -v ON_ERROR_STOP=1 -Atqc "SELECT 1 FROM pg_database WHERE datname = 'antimbench'" | grep -qx "1"; then
  runuser -u postgres -- psql --dbname=postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE antimbench OWNER antimbench_app"
else
  runuser -u postgres -- psql --dbname=postgres -v ON_ERROR_STOP=1 -c "ALTER DATABASE antimbench OWNER TO antimbench_app"
fi

cd "$(pwd)/backend"
/usr/local/bin/uv run --locked alembic upgrade head
