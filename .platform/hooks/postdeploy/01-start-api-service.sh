#!/bin/bash
set -euo pipefail

APP_DIR="$(pwd)"

cat >/etc/systemd/system/antimbench-api.service <<EOF
[Unit]
Description=AntimBench FastAPI service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
DynamicUser=yes
WorkingDirectory=${APP_DIR}/backend
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=${APP_DIR}/backend/runtime-site-packages
Environment=PROFILE_MEDIA_LOCAL_DIRECTORY=/var/lib/antimbench-api/profile-media
EnvironmentFile=-/opt/elasticbeanstalk/deployment/env
ExecStart=/usr/bin/python3.12 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
StateDirectory=antimbench-api
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=full

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/antimbench-notification-worker.service <<EOF
[Unit]
Description=AntimBench notification worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
DynamicUser=yes
WorkingDirectory=${APP_DIR}/backend
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=${APP_DIR}/backend/runtime-site-packages
EnvironmentFile=-/opt/elasticbeanstalk/deployment/env
ExecStart=/usr/bin/python3.12 -m app.workers.worker
Restart=always
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=full

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable antimbench-api.service
systemctl enable antimbench-notification-worker.service
systemctl restart antimbench-api.service
systemctl restart antimbench-notification-worker.service

for attempt in {1..12}; do
  if curl --fail --silent --show-error http://127.0.0.1:8000/health >/dev/null \
    && systemctl is-active --quiet antimbench-notification-worker.service; then
    exit 0
  fi
  sleep 5
done

systemctl --no-pager --full status antimbench-api.service
systemctl --no-pager --full status antimbench-notification-worker.service
exit 1
