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
```

**Check the system Python version before creating the venv** (`python3 --version`).
`gensim` (as of 4.4.0) has no prebuilt wheel for Python 3.12+ and its
Cython-generated C extensions fail to compile against those versions'
changed internals (`ma_version_tag`, `ob_digit`, etc. were removed/changed
in CPython 3.12-3.14) — confirmed failing on Ubuntu 26.04's default Python
3.14. If `python3 --version` is 3.12 or newer and no older `python3.1x` is
installable via apt/deadsnakes for your distro release, build one with
`pyenv` instead of using the system Python:

```bash
sudo apt install -y build-essential libssl-dev zlib1g-dev libbz2-dev \
  libreadline-dev libsqlite3-dev curl git libncursesw5-dev xz-utils \
  tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev

sudo -u wordbridge bash -c 'curl -fsSL https://pyenv.run | bash'
sudo -u wordbridge bash -c '
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
pyenv install 3.11.9
'
```

Then create the venv with whichever Python is actually compatible —
the system one if it's 3.11 or older, otherwise the pyenv-built one:

```bash
sudo -u wordbridge python3 -m venv .venv   # if system python3 is <= 3.11
# OR, if you had to build one with pyenv:
sudo -u wordbridge ~wordbridge/.pyenv/versions/3.11.9/bin/python3.11 -m venv .venv

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
