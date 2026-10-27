#!/usr/bin/env bash
# One-time setup of the GarageDesk demo on an Oracle Cloud Always Free ARM VM
# (VM.Standard.A1.Flex, Oracle Linux 9, rootless Podman with docker-compose v2),
# next to another site that already serves ports 80/443 from its own nginx container.
#
# Run as opc on the VM, with the Token Factory key in ~/garagedesk/garagedesk.env:
#   bash setup.sh
#
# Caddy takes over ports 80/443 and sends each host name to its app:
#   <ip>.sslip.io            -> GarageDesk
#   $OTHER_SITE_DOMAIN       -> the other site's nginx (moved to 127.0.0.1 only)
# Caddy fetches and renews Let's Encrypt certificates for both by itself.
set -euo pipefail

BASE=${GARAGEDESK_BASE:-$HOME/garagedesk}
REPO=${GARAGEDESK_REPO:-https://github.com/zhangshen20/garagedesk}
OTHER_SITE_DIR=${OTHER_SITE_DIR:-$HOME/nemsettlement}
OTHER_SITE_NETWORK=${OTHER_SITE_NETWORK:-nemsettlement_default}
OTHER_SITE_NGINX=${OTHER_SITE_NGINX:-nem-nginx}
export DOCKER_HOST=${DOCKER_HOST:-unix:///run/user/$(id -u)/podman/podman.sock}

IP=$(curl -fsS https://ifconfig.me || curl -fsS https://api.ipify.org)
SSLIP="${IP//./-}.sslip.io"
# GARAGEDESK_DOMAIN: your own name for the demo (an A record pointing at this VM); sslip.io keeps working too
HOST=${GARAGEDESK_DOMAIN:-$SSLIP}
SITE_NAMES=$HOST; [ "$HOST" = "$SSLIP" ] || SITE_NAMES="$HOST, $SSLIP"
echo "public address $IP, demo will be https://$HOST"

# 1. tools and disk: git for the checkout, and grow / into the rest of the boot volume
command -v git >/dev/null || sudo dnf install -y -q git
sudo /usr/libexec/oci-growfs -y >/dev/null 2>&1 && echo "root disk grown" || echo "root disk not grown (continuing)"
df -h / | tail -1

# 2. checkout and secrets
mkdir -p "$BASE"
[ -d "$BASE/src/.git" ] || git clone -q "$REPO" "$BASE/src"
git -C "$BASE/src" pull -q --ff-only origin main
[ -f "$BASE/garagedesk.env" ] || { echo "missing $BASE/garagedesk.env (NEBIUS_API_KEY=...)"; exit 1; }
grep -v '^PUBLIC_BASE_URL=' "$BASE/garagedesk.env" > "$BASE/src/.env"
echo "PUBLIC_BASE_URL=https://$HOST" >> "$BASE/src/.env"
chmod 600 "$BASE/garagedesk.env" "$BASE/src/.env"

# 3. Caddy in front of both sites (the other site's domain comes from its compose file)
OTHER_SITE_DOMAIN=${OTHER_SITE_DOMAIN:-$(grep -hoE 'DOMAIN[=:] *"?[A-Za-z0-9.-]+' "$OTHER_SITE_DIR"/docker-compose*.yml 2>/dev/null | head -1 | sed -E 's/.*[=:] *"?//')}
OTHER_BLOCK=""
if [ -n "$OTHER_SITE_DOMAIN" ] && podman network exists "$OTHER_SITE_NETWORK" 2>/dev/null; then
  OTHER_BLOCK="$OTHER_SITE_DOMAIN {
  reverse_proxy https://$OTHER_SITE_NGINX:443 {
    transport http {
      tls_insecure_skip_verify
    }
  }
}"
fi
cat > "$BASE/Caddyfile" <<CADDY
$SITE_NAMES {
  reverse_proxy garagedesk:8000
}
$OTHER_BLOCK
CADDY
cat > "$BASE/compose.local.yml" <<YML
name: garagedesk
services:
  garagedesk:
    ports: !reset []
  caddy:
    image: docker.io/library/caddy:2
    ports: ["80:80", "443:443"]
    volumes:
      - $BASE/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
    networks: [default$( [ -n "$OTHER_BLOCK" ] && echo ", other")]
    restart: unless-stopped
volumes:
  caddy-data:
$( [ -n "$OTHER_BLOCK" ] && printf 'networks:\n  other:\n    external: true\n    name: %s\n' "$OTHER_SITE_NETWORK")
YML
compose() { docker-compose --project-directory "$BASE/src" -f "$BASE/src/docker-compose.yml" -f "$BASE/compose.local.yml" "$@"; }

# 4. build and start the app while the other site keeps serving (takes a while on first run)
compose build garagedesk
compose up -d garagedesk

# 5. hand ports 80/443 to Caddy: the other site's nginx moves to 127.0.0.1:8080/8443
if [ -n "$OTHER_BLOCK" ] && [ -f "$OTHER_SITE_DIR/docker-compose.ssl.yml" ]; then
  F="$OTHER_SITE_DIR/docker-compose.ssl.yml"
  [ -f "$F.before-garagedesk" ] || cp "$F" "$F.before-garagedesk"
  sed -i -E 's/(["'"'"' -])(0\.0\.0\.0:)?80:80(["'"'"' ]|$)/\1127.0.0.1:8080:80\3/; s/(["'"'"' -])(0\.0\.0\.0:)?443:443(["'"'"' ]|$)/\1127.0.0.1:8443:443\3/' "$F"
  grep -q '127.0.0.1:8443:443' "$F" || { echo "could not move the other site's ports; left it as it was"; cp "$F.before-garagedesk" "$F"; exit 1; }
  (cd "$OTHER_SITE_DIR" && docker-compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --no-deps nginx)
fi
if ! compose up -d caddy; then
  echo "Caddy did not start; putting the other site back on 80/443"
  if [ -f "$OTHER_SITE_DIR/docker-compose.ssl.yml.before-garagedesk" ]; then
    cp "$OTHER_SITE_DIR/docker-compose.ssl.yml.before-garagedesk" "$OTHER_SITE_DIR/docker-compose.ssl.yml"
    (cd "$OTHER_SITE_DIR" && docker-compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --no-deps nginx)
  fi
  exit 1
fi

# 6. start on boot (after the other site's network exists) and follow main every 5 minutes
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/garagedesk.service <<UNIT
[Unit]
Description=GarageDesk demo and the Caddy front door
After=network-online.target podman.socket nemsettlement.service
Wants=podman.socket
[Service]
Type=oneshot
RemainAfterExit=yes
Environment=DOCKER_HOST=unix://%t/podman/podman.sock
ExecStart=/usr/local/bin/docker-compose --project-directory $BASE/src -f $BASE/src/docker-compose.yml -f $BASE/compose.local.yml up -d
[Install]
WantedBy=default.target
UNIT
cat > ~/.config/systemd/user/garagedesk-update.service <<UNIT
[Unit]
Description=Redeploy GarageDesk when main has moved on
[Service]
Type=oneshot
Environment=DOCKER_HOST=unix://%t/podman/podman.sock GARAGEDESK_BASE=$BASE
ExecStart=/bin/bash $BASE/src/deploy/oracle/self-update.sh
UNIT
cat > ~/.config/systemd/user/garagedesk-update.timer <<UNIT
[Unit]
Description=Check GarageDesk main for updates every 5 minutes
[Timer]
OnBootSec=3min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable garagedesk.service >/dev/null
systemctl --user enable --now garagedesk-update.timer >/dev/null
echo "boot service and self-update timer on"

for _ in $(seq 1 60); do
  curl -sf "https://$SSLIP/healthz" >/dev/null && { echo "live: https://$HOST/owner (also https://$SSLIP)"; exit 0; }
  sleep 5
done
echo "https://$SSLIP/healthz did not answer yet; check: docker logs garagedesk-caddy-1 / garagedesk-garagedesk-1"
exit 1
