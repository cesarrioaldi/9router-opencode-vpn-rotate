#!/usr/bin/env python3
"""Rotate NordVPN country when 9router-go hits an OpenCode free-usage 429 (macOS)."""
import json
import os
import random
import re
import subprocess
import sys
import time

HOME = os.path.expanduser(os.environ.get("NINEROUTER_HOME") or "~/.9router")
LOG = os.path.expanduser(os.environ.get("OPENCODE_VPN_LOG") or os.path.join(HOME, "run", "gateway.log"))
OUT = os.path.expanduser(os.environ.get("OPENCODE_VPN_OUT") or os.path.join(HOME, "run", "opencode-vpn-rotate.log"))
STATE = os.path.expanduser(os.environ.get("OPENCODE_VPN_STATE") or os.path.join(HOME, "run", "opencode-vpn-rotate.state"))
DB = os.path.expanduser(os.environ.get("OPENCODE_VPN_DB") or os.path.join(HOME, "db", "data.sqlite"))
DEFAULT_COUNTRIES = "se,fi,no,dk,ch,at,pl,cz,ro,hu,bg,gr,pt,es,it,ie,be,lu,ee,lv,lt,sk,si,hr,rs,ua,jp,sg,au,nz,br,ar,cl,mx,za,in,hk,tw,kr,th,my,id,ph,vn,us,de,gb,ca,nl,fr"
_countries = os.environ.get("OPENCODE_VPN_COUNTRIES", "").strip()
COUNTRIES = [c.strip() for c in (_countries or DEFAULT_COUNTRIES).split(",") if c.strip()]
MIN_INTERVAL = int(os.environ.get("OPENCODE_VPN_MIN_INTERVAL", "900"))
IP_TIMEOUT = int(os.environ.get("OPENCODE_VPN_IP_TIMEOUT", "45"))
MAX_TRIES = int(os.environ.get("OPENCODE_VPN_MAX_TRIES", "1"))
RECENT_KEEP = 3
API_URL = os.environ.get("OPENCODE_API_URL", "http://127.0.0.1:20130/v1/chat/completions")
MODEL = os.environ.get("OPENCODE_MODEL", "oc")
OPENCODE_RE = re.compile(r"(?:^|\s)provider=opencode(?:\s|$)")

for _path in (OUT, STATE):
    os.makedirs(os.path.dirname(_path) or ".", exist_ok=True)

last_rotate = 0.0
recent = []
failed_until = {}
api_key_cache = None
last_country = None


def load_state():
    global last_rotate
    try:
        with open(STATE, "r", encoding="utf-8") as f:
            last_rotate = float(f.read().strip())
    except (OSError, ValueError):
        last_rotate = 0.0


def save_state():
    try:
        with open(STATE, "w", encoding="utf-8") as f:
            f.write(str(last_rotate))
    except OSError:
        pass


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg
    print(line, flush=True)
    try:
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def run(cmd, timeout=10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


def public_ip():
    r = run(["/usr/bin/curl", "-s", "--max-time", "6", "https://api.ipify.org"], timeout=10)
    if r and r.returncode == 0:
        ip = r.stdout.strip()
        if re.fullmatch(r"[0-9a-fA-F:.]+", ip or ""):
            return ip
    return ""


def vpn_up():
    r = run(["/sbin/route", "-n", "get", "api.ipify.org"], timeout=5)
    return bool(r and r.returncode == 0 and "interface: utun" in r.stdout and "gateway: 10." in r.stdout)


def api_key():
    global api_key_cache
    if api_key_cache is not None:
        return api_key_cache
    key = os.environ.get("OPENCODE_API_KEY", "").strip()
    if not key:
        r = run(
            ["/usr/bin/sqlite3", DB, "select key from apiKeys where isActive=1 order by lastUsedAt desc limit 1;"],
            timeout=10,
        )
        if r and r.returncode == 0:
            key = r.stdout.strip()
    api_key_cache = key
    return key


def verify():
    key = api_key()
    if not key:
        return "no-key"
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1})
    r = run(
        [
            "/usr/bin/curl",
            "-s",
            "--max-time",
            "30",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            API_URL,
            "-H",
            "Authorization: Bearer " + key,
            "-H",
            "Content-Type: application/json",
            "-d",
            body,
        ],
        timeout=35,
    )
    if r and r.returncode == 0:
        return r.stdout.strip()
    return "000"


def pick_country():
    now = time.time()
    pool = [c for c in COUNTRIES if c not in recent and failed_until.get(c, 0) < now]
    if not pool:
        pool = [c for c in COUNTRIES if c not in recent]
    if not pool:
        pool = list(COUNTRIES)
    random.shuffle(pool)
    return pool[0] if pool else ""


def rotate(cc=None, force=False):
    global last_rotate, last_country
    if sys.platform != "darwin":
        log("rotate: unsupported platform (macOS only)")
        return False
    now = time.time()
    if not force and now - last_rotate < MIN_INTERVAL:
        log("skip rotation: cooldown %ds" % (MIN_INTERVAL - int(now - last_rotate)))
        return False
    old_ip = public_ip()
    if cc is None:
        cc = pick_country()
    if not cc:
        log("rotate: no country configured")
        return False
    last_country = cc
    log("rotate: country=%s old_ip=%s" % (cc, old_ip or "?"))
    run(["/usr/bin/open", "nordvpn://connect?country=" + cc], timeout=10)
    new_ip = ""
    deadline = time.time() + IP_TIMEOUT
    while time.time() < deadline:
        time.sleep(2)
        new_ip = public_ip()
        if new_ip and new_ip != old_ip:
            break
    last_rotate = time.time()
    save_state()
    up = vpn_up()
    if new_ip and new_ip != old_ip and up:
        recent.append(cc)
        if len(recent) > RECENT_KEEP:
            recent.pop(0)
        failed_until.pop(cc, None)
        log("rotate: connected country=%s new_ip=%s" % (cc, new_ip))
        return True
    failed_until[cc] = time.time() + 3600
    log("rotate: failed country=%s ip=%s vpn=%s" % (cc, new_ip or "?", "up" if up else "down"))
    return False


def handle_429():
    for attempt in range(MAX_TRIES):
        ok = rotate(force=(attempt > 0))
        if not ok:
            if attempt == 0:
                return
            continue
        code = verify()
        if code == "200":
            log("verify: opencode ok")
            return
        if code == "no-key":
            log("verify: no api key, rotation only")
            return
        if code == "429":
            if last_country:
                failed_until[last_country] = time.time() + 3600
            log("verify: still 429, cooling down country=%s" % last_country)
            continue
        log("verify: unexpected http=%s" % code)
        return
    if MAX_TRIES > 1:
        log("verify: gave up after %d countries" % MAX_TRIES)


class LogFollower:
    def __init__(self, path):
        self.path = path
        self.f = None
        self.ino = None
        self.open()

    def open(self):
        while True:
            try:
                self.f = open(self.path, "r", encoding="utf-8", errors="replace")
                break
            except FileNotFoundError:
                time.sleep(1)
        self.f.seek(0, os.SEEK_END)
        self.ino = os.fstat(self.f.fileno()).st_ino

    def readline(self):
        line = self.f.readline()
        if line:
            return line
        try:
            st = os.stat(self.path)
        except FileNotFoundError:
            return ""
        if st.st_ino != self.ino or st.st_size < self.f.tell():
            self.f.close()
            self.open()
        return ""

    def drain(self):
        while self.f.readline():
            pass


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] in ("-h", "--help"):
            print("usage: opencode-vpn-rotate.py [--ip|--vpn|--verify|--rotate [country]]")
            print("env: NINEROUTER_HOME, OPENCODE_VPN_LOG, OPENCODE_VPN_MIN_INTERVAL, OPENCODE_VPN_MAX_TRIES, OPENCODE_VPN_COUNTRIES, OPENCODE_API_URL, OPENCODE_MODEL, OPENCODE_API_KEY")
            return
        if sys.argv[1] == "--ip":
            print(public_ip())
            return
        if sys.argv[1] == "--verify":
            print(verify())
            return
        if sys.argv[1] == "--vpn":
            print("up" if vpn_up() else "down")
            return
        if sys.argv[1] == "--rotate":
            load_state()
            rotate(sys.argv[2] if len(sys.argv) > 2 else None)
            return
    load_state()
    log("watcher started")
    follower = LogFollower(LOG)
    while True:
        line = follower.readline()
        if not line:
            time.sleep(0.5)
            continue
        if OPENCODE_RE.search(line) and "FreeUsageLimitError" in line:
            log("detected opencode 429: " + line.strip()[:300])
            handle_429()
            time.sleep(1)
            follower.drain()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("watcher stopped")
