#!/bin/bash
set -euo pipefail

# This bundle targets the Elastic Beanstalk Node.js 22 Amazon Linux 2023 platform.
# The platform supplies Node.js; uv provisions the backend's required Python 3.12
# in a shared location so the runtime service can use the resulting virtualenv.
APP_DIR="$(pwd)"
UV_BIN="/usr/local/bin/uv"
export PATH="/usr/local/bin:${PATH}"
export UV_PYTHON_INSTALL_DIR="/opt/antimbench/python"

if [[ ! -x "${UV_BIN}" ]]; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi

install -d -m 0755 "${UV_PYTHON_INSTALL_DIR}"
"${UV_BIN}" python install 3.12

cd "${APP_DIR}/frontend"
npm ci --omit=dev

cd "${APP_DIR}/backend"
"${UV_BIN}" sync --locked --no-dev --no-editable

# The API is deliberately run as an unprivileged systemd DynamicUser.
chmod -R a+rX "${APP_DIR}/backend/.venv"
