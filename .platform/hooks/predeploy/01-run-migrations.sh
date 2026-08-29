#!/bin/bash
set -euo pipefail

# Platform hooks receive Elastic Beanstalk environment properties. The database
# URL is never bundled with the application version or written to disk.
: "${DATABASE_URL:?DATABASE_URL must be configured as an Elastic Beanstalk environment property.}"

# Production uses an existing managed PostgreSQL database. In particular, never
# initialise a local database, modify roles, create a database, or change
# ownership here: those operations would be unsafe for the configured RDS data.
case "${DATABASE_URL}" in
  postgresql://*|postgresql+psycopg2://*)
    echo "Using externally managed PostgreSQL."
    ;;
  *)
    echo "DATABASE_URL must use a PostgreSQL connection URL." >&2
    exit 1
    ;;
esac

BACKEND_DIR="$(pwd)/backend"
cd "${BACKEND_DIR}"
PYTHONPATH="${BACKEND_DIR}/runtime-site-packages" /usr/bin/python3.12 -m alembic upgrade head
