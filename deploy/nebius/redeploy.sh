#!/usr/bin/env bash
# Pull the latest main and rebuild on the VM. Run over SSH, or from the deploy workflow.
set -euo pipefail
cd /opt/garagedesk/src
git pull --ff-only origin main
docker compose up -d --build
docker image prune -f >/dev/null
for _ in $(seq 1 30); do curl -sf http://localhost/healthz && { echo " redeployed"; exit 0; }; sleep 2; done
echo "healthz did not come up"; exit 1
