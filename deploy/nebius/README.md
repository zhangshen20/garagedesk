# Deploying the demo on Nebius AI Cloud

One small CPU VM (`cpu-d3` / `2vcpu-8gb`, Ubuntu 24.04) runs the Docker image behind Caddy. The models stay on Nebius Token Factory; the VM just needs the API key.

## One-time

1. In the Nebius console note your **project id** (`project-e00…`). Optionally create a **service account** with an authorized key if deploying from CI or a cloud session; a laptop with `nebius` logged in works without one.
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

3. Set `PUBLIC_BASE_URL=http://<ip>` in `/opt/garagedesk/src/.env` on the VM (it goes into the invoice links texted to customers) and run `bash deploy/nebius/redeploy.sh` there once.

## Updates

Add repository secrets `DEPLOY_HOST`, `DEPLOY_USER` (`ubuntu`), `DEPLOY_SSH_KEY` and every green CI run on `main` redeploys automatically (`.github/workflows/deploy.yml`). Or SSH in and run `redeploy.sh`.

## HTTPS

Point a DNS name at the IP, change the Caddyfile's `:80` to that name, and `docker compose up -d`; Caddy fetches a certificate automatically.

## Notes

- The VM's cloud-init contains the Token Factory key; keep `deploy.sh` output and the VM's `.env` out of version control.
- To tear down: `nebius compute instance delete --id <id>`.
