# Deploying Wordbridge

Local development is unaffected by any of this — keep using `./server.sh`
(or `server.bat` on Windows) to run `python app.py` directly, exactly as
before.

This guide is for running Wordbridge on a real server (e.g. an OVHcloud
VPS-2: 4 vCore / 8GB RAM / 75GB NVMe) so it survives crashes and reboots.

## 1. One-time server setup

SSH into the VPS, then:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git

sudo useradd --system --create-home --shell /usr/sbin/nologin wordbridge
sudo mkdir -p /opt/wordbridge
sudo chown wordbridge:wordbridge /opt/wordbridge

sudo -u wordbridge git clone <your-repo-url> /opt/wordbridge
cd /opt/wordbridge
sudo -u wordbridge python3 -m venv .venv
sudo -u wordbridge .venv/bin/pip install -r requirements.txt
```

The first run downloads the ~3.6GB word2vec model via gensim — do this
once manually so you can watch it succeed before handing control to
systemd:

```bash
sudo -u wordbridge .venv/bin/python app.py
# wait for "Model loaded.", then Ctrl+C
```

## 2. Install the systemd service

```bash
sudo cp deploy/wordbridge.service /etc/systemd/system/wordbridge.service
sudo systemctl edit wordbridge   # or just edit the file directly
```

Before starting it, replace `REPLACE_WITH_A_LONG_RANDOM_VALUE` in the
service file with a real secret (`python3 -c "import secrets; print(secrets.token_hex(32))"`).
Without a fixed `SECRET_KEY`, every restart invalidates everyone's
in-progress session — fine for local dev, not what you want in production.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wordbridge
sudo systemctl status wordbridge
```

`Restart=on-failure` in the unit file is the "restart if it crashes" job
you asked about — systemd handles it natively, no separate script needed.
It also starts the app automatically on reboot (`enable`).

The app is now reachable at `http://<vps-ip>:8000`.

**Important:** `--workers 1` in the service file is deliberate, not a
typo. Each gunicorn worker is a separate process that loads its own full
copy of the word2vec model — running more than one worker multiplies RAM
usage (2 workers ≈ 8GB+ just for vectors). One worker easily handles a
low-traffic personal project.

## 3. Updating after a code change

```bash
cd /opt/wordbridge
sudo -u wordbridge git pull
sudo -u wordbridge .venv/bin/pip install -r requirements.txt
sudo systemctl restart wordbridge
```

## 4. Optional: a real domain + HTTPS

The steps above serve plain HTTP directly from gunicorn on port 8000 —
fine to start with. To put it behind a domain with a free TLS cert
later, add nginx as a reverse proxy (`sudo apt install nginx`, proxy
`/` to `127.0.0.1:8000`, then `certbot --nginx`) and change the service
file's bind address to `127.0.0.1:8000` so gunicorn isn't directly
exposed. Not required to get running.
