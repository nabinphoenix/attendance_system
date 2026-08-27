#!/bin/bash
set -euo pipefail

# This bundle targets the Elastic Beanstalk Node.js 22 Amazon Linux 2023 platform.
# Node's traced runtime and the backend's locked Python packages are built in
# GitHub Actions and included in the bundle. Keep this hook limited to the OS
# packages that must be installed on the instance.
APP_DIR="$(pwd)"
BACKEND_DIR="${APP_DIR}/backend"

# Amazon Linux 2023 provides PostgreSQL 15 through these versioned packages.
# `python3.12` supplies the target interpreter for the prebuilt site-packages.
# dnf safely reports packages as already installed on later deployments.
dnf install -y --setopt=install_weak_deps=False \
  postgresql15 postgresql15-server python3.12

if [[ ! -d "${BACKEND_DIR}/runtime-site-packages" ]]; then
  echo "The deployment bundle is missing the prebuilt backend runtime packages." >&2
  exit 1
fi

# The API is deliberately run as an unprivileged systemd DynamicUser.
chmod -R a+rX "${BACKEND_DIR}/runtime-site-packages"
