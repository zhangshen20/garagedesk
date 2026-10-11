#!/usr/bin/env bash
# Pull the latest main and rebuild on the VM. Run over SSH, or from the deploy workflow.
set -euo pipefail
cd /opt/garagedesk/src
git pull --ff-only origin main
docker compose up -d --build
docker image prune -f >/dev/null
curl -sf http://localhost/healthz && echo " redeployed"
