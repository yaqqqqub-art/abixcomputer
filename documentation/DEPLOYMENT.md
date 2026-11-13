# Deployment (V1 + Stage 1 + Stage 2)

## Requirements
- Linux server (Ubuntu 22.04/24.04 recommended), 2+ CPU cores, 4 GB+ RAM, 20 GB+ disk
- Docker Engine and the Compose plugin
- Open ports 80 and 443 (only these; never open 5901 or 6080)

## Steps
```bash
cd abix-cloud-computer
bash deployment/init.sh your.domain.or.ip   # creates .env, login, self-signed certificate
docker compose up -d --build
bash tests/smoke.sh
```
Open `https://your-server/` and sign in on the web page with the login from `deployment/first-login.txt`.
Change the password later: `bash deployment/set-password.sh && docker compose up -d`.
A self-signed certificate makes the browser show a warning; that is expected until you install a real one.

## Real HTTPS certificate
Point a domain to the server, obtain a certificate (for example with certbot), and place
`fullchain.pem` and `privkey.pem` in `deployment/certs/`, then `docker compose restart nginx`.

## Try it on a Windows PC
Install Docker Desktop (WSL2 backend), open a WSL/Ubuntu or Git Bash terminal, and run the same steps.
This is only for testing; the desktop then runs on your own PC, not in the cloud.

## Reset
`docker compose down` keeps your files. `docker compose down -v` deletes the workspace volume.
