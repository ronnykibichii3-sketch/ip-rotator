# IP Rotator

A small, transparent tool that starts at login, asks for a password, and then
rotates your connection between VPN servers.

## Important realities

- **"New IP every second" is not possible.** A VPN reconnect needs 2–10 seconds
  (handshake, route change). Switching every second means the tunnel never
  comes up. The minimum allowed interval in this tool is **30 s**; the default
  is 300 s.
- **Rapid reconnects get you rate-limited.** Proton VPN throttles or locks
  accounts that reconnect in a tight loop.
- **Every rotation drops connections.** Downloads, SSH, video calls and logins
  break each time.
- **For privacy, one stable VPN server is better** than rotating. Constant IP
  changes make you *more* fingerprintable, not less.

## Password

Set to `202005` as requested. It is stored only as a PBKDF2-SHA256 hash in
`config.json` (never in plain text). Change it any time:

```bash
python3 ~/ip-rotator/ip_rotator.py --set-password
```

> A script-level password is only a speed bump. Anyone with your Linux account
> can read the script and the config. Do not reuse a real password here.

## Setup A — Proton VPN WireGuard profiles (recommended)

1. Install the Proton VPN app and log in **once** with your email/password.
   The app stores the session; this tool never sees your Proton password.
2. In the Proton dashboard (Account → Downloads → WireGuard configuration),
   download a few country configs.
3. Import each one into NetworkManager and give it a short name, e.g.:

```bash
sudo nmcli connection import type wireguard file ~/Downloads/proton-nl.conf
sudo nmcli connection modify proton-nl connection.id proton-nl
```

4. Put the names in `~/ip-rotator/config.json`:

```json
"profiles": ["proton-nl", "proton-de", "proton-ch", "proton-us"]
```

5. Test once:

```bash
python3 ~/ip-rotator/ip_rotator.py --status
python3 ~/ip-rotator/ip_rotator.py --once
```

## Setup B — official Proton VPN CLI (proton-vpn-cli)

Do **not** use the old `protonvpn-cli` from PyPI (2021, unmaintained, breaks on
Python 3.14). Use Proton's official CLI instead.

Install (needs root):

```bash
cd ~/Downloads
sudo dnf install ./protonvpn-stable-release.rpm
sudo dnf check-update --refresh
sudo dnf install proton-vpn-cli
```

Sign in once, then test:

```bash
protonvpn signin            # enter your Proton email + password
protonvpn connect --country NL
protonvpn disconnect
```

The tool then rotates using `config.json`:

```json
"profiles": [],
"protonvpn_cli": "protonvpn",
"proton_selection": "random",
"proton_servers": ["NL", "DE", "CH", "US", "SE"]
```

`proton_selection` controls what is passed to `protonvpn connect`:

| Value | Command | Plan needed |
|---|---|---|
| `random` | `protonvpn connect --random` | **Paid** (VPN Plus) |
| `country` | `protonvpn connect --country <code>` | **Paid** (VPN Plus) |

The official CLI needs NetworkManager and a Secret Service provider
(`gnome-keyring` or a compatible KWallet). It does not work headless.

### Verified limitation: free plan cannot rotate

Tested on 2026-11-13 with a free Proton account:

| Command | Result |
|---|---|
| `protonvpn connect` | always `NL-FREE#252` → `185.100.233.203` (3/3 attempts) |
| `protonvpn connect --random` | `Error: Random selection is not available on the free plan` |
| `protonvpn connect --country NL` | `Error: Location selection is not available on the free plan` |
| `protonvpn connect US-FREE#1` | `Error: Server selection by ID is not available on the free plan` |

So on the free plan the IP is fixed. The daemon detects this error and **stops
cleanly** instead of reconnecting in a loop. Options:

1. **Upgrade to Proton VPN Plus** — then `proton_selection: "random"` works and
   the daemon rotates on every interval.
2. **Stay free** — use plain `protonvpn connect` for one stable VPN IP. No
   rotation, but your real IP is hidden.
3. **Use WireGuard profiles** (Setup A) — you can import as many servers as your
   plan allows and rotate with `nmcli`.

Circumventing the plan check is not supported: it breaks Proton's terms of
service.

## Setup C — any provider with downloadable configs (works on free plans)

The rotator can drive **any** WireGuard `.conf` or OpenVPN `.ovpn` file, so a
multi-endpoint provider entirely sidesteps Proton's CLI selection limit. This
is the route to use on a free Proton account.

### 1. Get config files

**A. Proton free WireGuard configs (trusted, same account)**
Sign in at `account.protonvpn.com` → **Downloads → WireGuard configuration**.
Create one config per server/country offered to you and download each `.conf`.
Free accounts can generate these; you just cannot pick paid servers. This is a
normal feature, not a workaround.

**B. VPN Gate (free, no account, many countries, untrusted servers)**

```bash
cd ~/ip-rotator
python3 fetch_vpngate.py --count 6          # writes ./profiles/*.ovpn
python3 fetch_vpngate.py --list             # see what is available
```

These are volunteer-operated relays. Fine for geo-testing; **never** use them
for banking or account logins.

**C. Paid providers (best privacy per euro)**
Mullvad (€5/month, no email needed), IVPN, or Proton VPN Plus all let you
download WireGuard configs for every location. Same steps as below.

### 2. Import into NetworkManager

Put every `.conf`/`.ovpn` in `~/ip-rotator/profiles/`, then:

```bash
python3 ~/ip-rotator/import_profiles.py --dry-run   # preview, no sudo
python3 ~/ip-rotator/import_profiles.py             # asks for your sudo password
```

The importer:

- runs `nmcli connection import type wireguard|openvpn file …`
- renames each connection to `ipr-<filename>`
- sets `connection.autoconnect no` (so boot does not hijack your network)
- appends the names to `config.json → "profiles"`

Check it:

```bash
python3 ~/ip-rotator/import_profiles.py --list
```

### 3. Randomise the order

`config.json`:

```json
"profiles": ["ipr-us-…", "ipr-jp-…", "ipr-kr-…"],
"random_profiles": true
```

With `random_profiles: true` the daemon picks a random profile different from
the current one each cycle. With `false` it cycles through the list in order.

### 4. Run

```bash
python3 ~/ip-rotator/ip_rotator.py --once     # password 202005
python3 ~/ip-rotator/ip_rotator.py --daemon
tail -f ~/ip-rotator/rotator.log
```

Remove everything later:

```bash
python3 ~/ip-rotator/import_profiles.py --remove
```

## Start at login

`~/.config/autostart/ip-rotator.desktop` already does this. It launches the
daemon, which shows a password dialog, then runs in the background.

Disable autostart:

```bash
rm ~/.config/autostart/ip-rotator.desktop
```

## Commands

```bash
python3 ~/ip-rotator/ip_rotator.py --set-password   # change password
python3 ~/ip-rotator/ip_rotator.py --status         # current public IP
python3 ~/ip-rotator/ip_rotator.py --once           # rotate one step
python3 ~/ip-rotator/ip_rotator.py --daemon         # run the loop
python3 ~/ip-rotator/ip_rotator.py --stop           # stop the loop
```

Logs: `~/ip-rotator/rotator.log`

## Note on use

Rotating IPs to protect your own privacy is fine. Using it to evade bans,
fake multiple accounts, or commit fraud is against Proton's terms and, in many
places, illegal. Don't do that.
## OS Support & Installation

| OS                | Native support | Notes |
|-------------------|----------------|-------|
| **Linux** (any distro with NetworkManager) | ✅ Yes | `nmcli` is available; the rotator works out‑of‑the‑box. |
| **Ubuntu**        | ✅ Yes | Same as Linux – NetworkManager is default. |
| **Linux Mint**    | ✅ Yes | Same as Linux – NetworkManager is default. |
| **Windows**       | ❌ No | `nmcli` / NetworkManager are not present natively. Use **WSL 2** (see below). |

### Quick one‑liner commands per OS

| OS                | Install deps | Import profiles | Run daemon |
|-------------------|--------------|-----------------|-----------|
| **Ubuntu / Mint / Debian** | `sudo apt update && sudo apt install -y python3 git` | `python3 import_profiles.py` | `python3 ip_rotator.py --daemon` |
| **Fedora / RHEL / CentOS** | `sudo dnf install -y NetworkManager` then `sudo systemctl start/enable NetworkManager` | same as above | same as above |
| **Windows (via WSL 2)** | Inside the Ubuntu WSL terminal: `sudo apt update && sudo apt install -y python3 git` | same as above | same as above |
| **Windows (native)** | Install **OpenVPN GUI** or **Proton VPN CLI** manually (no automated rotation) | N/A (manual) | N/A (manual) |

### Using the rotator on Windows (WSL 2)

1. **Install WSL 2** (PowerShell as Administrator):  
   ```powershell
   wsl --install -d Ubuntu
   ```
2. **Restart** your machine, then open **Ubuntu** from the Start menu.
3. **Copy or clone the ip‑rotator files** inside WSL:  
   ```bash
   git clone https://github.com/your-repo/ip-rotator.git ~/ip-rotator
   # or, if you already have a Windows copy:
   cp -r /path/to/windows/copy ~/ip-rotator
   ```
4. **Install dependencies** (once inside the Ubuntu terminal):  
   ```bash
   sudo apt update
   sudo apt install -y python3 git
   ```
5. **Import VPN profiles** (choose your source – Proton VPN, VPN Gate, or any .conf/.ovpn files):  
   ```bash
   python3 ~/ip-rotator/import_profiles.py
   ```
6. **Start the daemon** (first run will ask for a password):  
   ```bash
   python3 ~/ip-rotator/ip_rotator.py --daemon
   ```
7. **Rotate once & exit** (useful for testing):  
   ```bash
   python3 ~/ip-rotator/ip_rotator.py --once
   ```
8. **Check your public IP**:  
   ```bash
   python3 ~/ip-rotator/ip_rotator.py --status
   ```
9. **Change the access password** (if needed):  
   ```bash
   python3 ~/ip-rotator/ip_rotator.py --set-password
   ```
10. **Stop the daemon** when you’re done:  
    ```bash
    python3 ~/ip-rotator/ip_rotator.py --stop
    ```

*All of the above commands are **identical** to the Linux workflow; nothing in the original `/home/ronny/ip-rotator` folder has been modified.*

---
