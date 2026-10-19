#!/usr/bin/env bash
# Pull the latest main and rebuild on the VM. Run over SSH, or from the deploy workflow.
set -euo pipefail
cd /opt/garagedesk/src
git pull --ff-only origin main
docker compose up -d --build
docker image prune -f >/dev/null
# keep the VM following main from now on (self-update.sh, every 5 minutes)
if [ -d /etc/systemd/system ] && [ ! -f /etc/systemd/system/garagedesk-update.timer ]; then
  cat > /etc/systemd/system/garagedesk-update.service <<'UNIT'
[Unit]
Description=Redeploy GarageDesk when main has moved on
[Service]
Type=oneshot
ExecStart=/bin/bash /opt/garagedesk/src/deploy/nebius/self-update.sh
UNIT
  cat > /etc/systemd/system/garagedesk-update.timer <<'UNIT'
[Unit]
Description=Check GarageDesk main for updates every 5 minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
UNIT
  systemctl daemon-reload && systemctl enable --now garagedesk-update.timer && echo "self-update timer on"
fi
for _ in $(seq 1 30); do curl -sf http://localhost/healthz && { echo " redeployed"; exit 0; }; sleep 2; done
echo "healthz did not come up"; exit 1
