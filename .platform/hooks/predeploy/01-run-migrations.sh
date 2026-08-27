#!/bin/bash
set -euo pipefail

# Platform hooks receive Elastic Beanstalk environment properties. DATABASE_URL is
# configured in Elastic Beanstalk, never bundled with the application version.
: "${DATABASE_URL:?DATABASE_URL must be configured as an Elastic Beanstalk environment property.}"

cd "$(pwd)/backend"
/usr/local/bin/uv run --locked alembic upgrade head
