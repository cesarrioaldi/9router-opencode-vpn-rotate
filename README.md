# 9router OpenCode VPN Rotator

A small macOS watcher for 9router-go. When the `opencode` provider returns its free-usage limit (`429 FreeUsageLimitError`), it asks the NordVPN app to switch to another country, verifies the new egress IP, and then waits before trying again.

It is deliberately slow: **one rotation per 15 minutes** by default, **one country per event**. It is a fallback, not a guarantee that a fresh IP is available.

> **Unofficial.** This is not affiliated with 9router, OpenCode, or NordVPN. Rotating IPs to avoid free-tier limits may violate the provider's terms. Use at your own risk.

## Requirements

- macOS. The script uses the NordVPN macOS app and `launchd`.
- NordVPN app installed and signed in (`/Applications/NordVPN.app`).
- An active NordVPN account. The script does **not** provide NordVPN access and does **not** need service credentials or SOCKS5.
- 9router-go running on `127.0.0.1:20130`.
- Python 3.9+ (`/usr/bin/python3` is fine).
- 9router-go log at `~/.9router/run/gateway.log` (configurable).

No Docker, Go, Node, root access, or kernel extension is required.

## Install

```bash
git clone https://github.com/cesarrioaldi/9router-opencode-vpn-rotate.git
cd 9router-opencode-vpn-rotate
./install.sh
```

The installer:

1. Copies the watcher to `~/.9router/opencode-vpn-rotate.py`.
2. Creates `~/Library/LaunchAgents/com.9router.opencode-vpn-rotate.plist`.
3. Loads and starts the LaunchAgent.

It does not use `sudo`.

## How it works

```text
9router-go log
   │  tail only new lines
   ▼
[watcher] ── exact provider=opencode + FreeUsageLimitError?
   │ yes
   ▼
15-minute cooldown finished?
   │ no  ──> log and do nothing
   │ yes
   ▼
read current public IP ─> pick country ─> open nordvpn://connect?country=xx
   │
   ▼
wait for public IP to change (max 45 seconds)
   │
   ▼
confirm VPN is really up: route uses utun + gateway 10.x
   │
   ▼
verify through local 9router: model oc, max_tokens=1
   ├─ 200 -> success
   ├─ 429 -> cool that country down for 1 hour, wait for next window
   └─ other -> log it, do not spam
```

Key details:

- The watcher starts at the **end** of the log. Old 429 lines are ignored.
- It only reacts to the exact provider `opencode`. Keyed providers such as `opencode-zen` and `opencode-go` are not matched.
- The request that produced the 429 is **not replayed**. It already failed. The next request after the IP change uses the new IP.
- The last 3 countries used in the current run are avoided.
- A country that still returns 429 is cooled down for 1 hour in memory.
- The route check prevents a false success: if Nord force-disconnects and the IP becomes the real IP, the watcher treats it as a failed rotation.
- The verification request is tiny (`max_tokens: 1`) but it still consumes a small amount of quota.

## Safety and privacy

- **No root.** It runs as your user through a LaunchAgent.
- **No 9router changes.** It does not modify 9router settings, proxy pools, or the database. The database is queried read-only for an API key.
- **No secrets in the repo or plist.** The API key is read from the 9router database at runtime, or from `OPENCODE_API_KEY`.
- **No telemetry.** The only outbound calls are:
  - `api.ipify.org` to read the current public IP,
  - the NordVPN app through `nordvpn://connect`,
  - the local 9router API for verification.
- **Local state only.** Logs and the cooldown timestamp stay in `~/.9router/run/`.
- **One-command stop.** Unload the LaunchAgent or run `./uninstall.sh`.
- **Readable source.** The watcher is one Python file; there is no compiled binary.

## What it does not do

- It does not create a VPN or provide NordVPN access.
- It does not remove the need for an active NordVPN account.
- It does not retry the failed request.
- It does not guarantee a clean IP; shared Nord IPs can also be rate-limited.
- It does not disconnect Nord first. If it switches while Nord is connected, Nord may hit its connection limit and force-disconnect. The watcher detects this as a failure and waits.
- It does not work on Windows, Linux, or mobile.

## Commands

```bash
python3 ~/.9router/opencode-vpn-rotate.py --ip
python3 ~/.9router/opencode-vpn-rotate.py --vpn
python3 ~/.9router/opencode-vpn-rotate.py --verify
python3 ~/.9router/opencode-vpn-rotate.py --rotate se
```

`--rotate` respects the cooldown. To reset the cooldown, remove `~/.9router/run/opencode-vpn-rotate.state` or wait.

`--verify` uses the API key from the 9router database or `OPENCODE_API_KEY`.

## Logs

```bash
tail -f ~/.9router/run/opencode-vpn-rotate.log
```

## Stop / uninstall

```bash
./uninstall.sh
```

Or stop it without removing files:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.9router.opencode-vpn-rotate.plist
```

## Configuration

Set these environment variables before running `./install.sh`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `NINEROUTER_HOME` | `~/.9router` | 9router data directory |
| `OPENCODE_VPN_LOG` | `$NINEROUTER_HOME/run/gateway.log` | log file to watch |
| `OPENCODE_VPN_MIN_INTERVAL` | `900` | seconds between rotations |
| `OPENCODE_VPN_MAX_TRIES` | `1` | countries tried per 429 event |
| `OPENCODE_VPN_COUNTRIES` | built-in list | comma-separated ISO country codes |
| `OPENCODE_VPN_IP_TIMEOUT` | `45` | seconds to wait for a new IP |
| `OPENCODE_API_URL` | `http://127.0.0.1:20130/v1/chat/completions` | verification endpoint |
| `OPENCODE_MODEL` | `oc` | model used for verification |
| `PYTHON` | `/usr/bin/python3` | Python interpreter |

`OPENCODE_API_KEY` is optional. The installer does not put it in the plist. If the 9router database is unavailable, set it in the plist manually and restrict the file:

```bash
chmod 600 ~/Library/LaunchAgents/com.9router.opencode-vpn-rotate.plist
```

Example:

```bash
OPENCODE_VPN_MIN_INTERVAL=1800 ./install.sh
```

## Verify it yourself

```bash
less ~/.9router/opencode-vpn-rotate.py
python3 ~/.9router/opencode-vpn-rotate.py --vpn
python3 ~/.9router/opencode-vpn-rotate.py --ip
python3 ~/.9router/opencode-vpn-rotate.py --verify
plutil -p ~/Library/LaunchAgents/com.9router.opencode-vpn-rotate.plist
```

## Limitations

- macOS only.
- NordVPN app must be signed in and the account must be active.
- Country history and cooldowns are in memory; a watcher restart forgets them. The last rotation timestamp survives.
- It does not disconnect first. Switching while connected can trigger Nord's connection limit.
- Nord shared IPs may also be rate-limited by OpenCode. The watcher is a fallback, not a guarantee.
- Rotating IPs to bypass free-tier limits may violate the provider's terms. Use at your own risk.
- No API key is stored in this repository. The LaunchAgent plist stores paths and settings only by default.

## Files

- `opencode-vpn-rotate.py` — watcher.
- `install.sh` — installs and starts the LaunchAgent.
- `uninstall.sh` — stops and removes it.
