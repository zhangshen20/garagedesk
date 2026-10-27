# Running the demo on an Oracle Cloud Always Free VM

The demo also runs on Oracle's free ARM VM (`VM.Standard.A1.Flex`, 4 OCPU / 24 GB, Oracle Linux 9). The image builds natively for arm64 (onnxruntime, CTranslate2, PyAV and espeak-ng all ship aarch64 wheels). All model calls still go to Nemotron on Nebius Token Factory.

From the laptop, with the keys in `~/Code/garagedesk/.env.deploy` (`NEBIUS_API_KEY`, `TAVILY_API_KEY`):

```bash
bash deploy/oracle/install-from-mac.sh     # ORACLE_VM=opc@<ip> ORACLE_SSH_KEY=~/.ssh/<key> to override
```

It copies the keys to `~/garagedesk/garagedesk.env` on the VM and runs `setup.sh` there, which:

- installs git and grows `/` into the unused part of the boot volume (`oci-growfs`);
- clones the repo to `~/garagedesk/src` and builds the image with rootless Podman and docker-compose v2;
- puts Caddy on ports 80/443 with a Let's Encrypt certificate for `<ip>.sslip.io`. If another site's nginx container already holds 80/443, it is moved to `127.0.0.1:8080/8443` and Caddy forwards that site's domain to it (its compose file is backed up as `*.before-garagedesk`);
- adds user systemd units: `garagedesk.service` (start on boot) and `garagedesk-update.timer` (follow `main` every 5 minutes, `self-update.sh`).

Logs: `journalctl --user -u garagedesk-update`, `docker logs garagedesk-garagedesk-1`, `docker logs garagedesk-caddy-1`.

Always Free instances that stay idle for a week can be reclaimed by Oracle; upgrading the tenancy to Pay As You Go keeps them free and stops that.
