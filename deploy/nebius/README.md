# Deploying the demo on Nebius AI Cloud

One small CPU VM (`cpu-d3` / `2vcpu-8gb`, Ubuntu 24.04) runs the Docker image behind Caddy. The models stay on Nebius Token Factory; the VM just needs the API key.

## One-time

1. In the Nebius console note your **project id** (`project-e00…`). Each region has its own default project; pick one whose `compute.instance.non-gpu.vcpu` quota is above zero (`nebius quotas quota-allowance list --parent-id <tenant-id>`). New tenants get 0 CPU vCPUs in eu-north1 and us-central1, so the demo runs in eu-west1. Billing must be active on the tenant, otherwise every create returns `PermissionDenied`. Optionally create a **service account** with an authorized key if deploying from CI or a cloud session; a laptop with `nebius` logged in works without one.
2. Run:

```bash
export NEBIUS_PROJECT_ID=project-e00xxxx
export NEBIUS_API_KEY=...            # Token Factory key, baked into the VM's .env
export TAVILY_API_KEY=...            # optional
# only for service-account auth:
# export NEBIUS_SA_ID=... NEBIUS_PUBLIC_KEY_ID=... NEBIUS_SA_PRIVATE_KEY="$(cat key.pem)"
bash deploy/nebius/deploy.sh
```

It prints the public IP. About three minutes later `http://<ip>/` serves the dashboard and `http://<ip>/chat` the customer page.

The VM's cloud-init also authorizes `~/.ssh/id_ed25519.pub` (override with `SSH_PUBKEY_FILE`) for user `ubuntu`.

3. Set `PUBLIC_BASE_URL=http://<ip>` in `/opt/garagedesk/src/.env` on the VM (it goes into the invoice links texted to customers) and run `sudo bash deploy/nebius/redeploy.sh` there once (the `.env` and checkout are root-owned).

## Updates

The first `redeploy.sh` run installs `garagedesk-update.timer`: every 5 minutes the VM fetches `main` and, when it has moved on, runs `redeploy.sh` itself (`self-update.sh`). So anything merged to `main` is live within a few minutes. `journalctl -u garagedesk-update` shows what it did; `systemctl disable --now garagedesk-update.timer` turns it off.

Alternatively, add repository secrets `DEPLOY_HOST`, `DEPLOY_USER` (`ubuntu`), `DEPLOY_SSH_KEY` and every green CI run on `main` redeploys automatically (`.github/workflows/deploy.yml`). Or SSH in and run `redeploy.sh`.

## HTTPS

The owner app needs HTTPS: iPhone Safari only allows speech recognition on a secure page. With no domain, use the free sslip.io name for the IP (`66.201.4.40` becomes `66-201-4-40.sslip.io`). Add a site block for it to the VM's Caddyfile next to `:80`, set `PUBLIC_BASE_URL=https://66-201-4-40.sslip.io` in `.env` so texted links use it, and `docker compose up -d`; Caddy fetches a Let's Encrypt certificate automatically.

```
66-201-4-40.sslip.io {
  reverse_proxy garagedesk:8000
}
:80 {
  reverse_proxy garagedesk:8000
}
```

## Notes

- The VM's cloud-init contains the Token Factory key; keep `deploy.sh` output and the VM's `.env` out of version control.
- To tear down: `nebius compute instance delete --id <id>`.
