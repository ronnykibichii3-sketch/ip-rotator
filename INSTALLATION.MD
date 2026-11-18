# IP Rotator — Installation Guide per OS

This guide explains how to install and run the IP Rotator on the most common operating systems.
The **code itself is unchanged** — it remains the same Python script that works wherever
NetworkManager (and `nmcli`) is available, plus a few helper scripts.

## :warning: Supported OS status

| OS          | Native support | Notes |
|-------------|----------------|-------|
| **Linux**   | ✅ Yes         | Works out‑of‑the‑box on any distro with NetworkManager (Ubuntu, Mint, Fedora, Debian, Arch, etc.). |
| **Windows** | ❌ No          | `nmcli` (NetworkManager) is not available natively. See the “Windows” section below. |
| **Ubuntu**  | ✅ Yes         | Same as Linux – NetworkManager is default. |
| **Linux Mint** | ✅ Yes     | Same as Linux – NetworkManager is default. |

If you are on Windows and want to use the rotator, the recommended path is to use **WSL 2** (Windows Subsystem for Linux) and follow the Linux instructions inside a Ubuntu‑based distribution.

## 1️⃣ Linux (Ubuntu, Debian, Mint, elementary OS, etc.)

NetworkManager is installed by default on these distributions. The rotator relies on `nmcli`,
which is part of the `network-manager` package.

### Install dependencies

```bash
# Update package lists
sudo apt update

# Install Python 3 (if not already present)
sudo apt install -y python3 python3-pip

# (Optional) install git for cloning/repo management
sudo apt install -y git
```

### Get the ip‑rotator files

```bash
# Clone the repository (or download the ZIP and extract)
git clone https://github.com/your-repo/ip-rotator.git ~/ip-rotator
cd ~/ip-rotator
```

### Import VPN profiles

The rotator can work with three profile sources. Choose the one you prefer.

#### A — Proton VPN WireGuard (recommended, needs Proton account)

```bash
# 1. Install the Proton VPN app once, log in, then download WireGuard configs
#    from the Proton dashboard (Account → Downloads → WireGuard configuration).

# 2. Import each config into NetworkManager (you will be asked for your sudo password):
python3 ~/ip-rotator/import_profiles.py
#    – this runs `nmcli connection import type wireguard file …`
#    – connections are named `ipr-<filename>` and added to config.json

# 3. Verify the imported profiles:
python3 ~/ip-rotator/import_profiles.py --list
```

#### B — VPN Gate free configs (no account needed)

```bash
# 1. Fetch a few free VPN‑Gate OpenVPN configs:
python3 ~/ip-rotator/fetch_vpngate.py --count 6

# 2. Import them into NetworkManager:
python3 ~/ip-rotator/import_profiles.py
```

#### C — Any provider with downloadable WireGuard/OpenVPN configs

```bash
# Place your .conf / .ovpn files inside ~/ip-rotator/profiles/
# Then import:
python3 ~/ip-rotator/import_profiles.py
```

### Run the rotator

```bash
# Start the daemon (it will ask for a password on first run)
python3 ~/ip-rotator/ip_rotator.py --daemon

# Optional: run a single rotation and exit
python3 ~/ip-rotator/ip_rotator.py --once

# Check your current public IP
python3 ~/ip-rotator/ip_rotator.py --status

# Change the access password
python3 ~/ip-rotator/ip_rotator.py --set-password

# Stop a running daemon
python3 ~/ip-rotator/ip_rotator.py --stop
```

> **First‑run password** – The first time you launch the daemon it will pop up a
> graphical password prompt (KDE/zenity). Choose a password and remember it; it is
> stored as a PBKDF2‑SHA256 hash in `config.json`.

### Autostart (optional)

A desktop entry is already included (`~/.config/autostart/ip-rotator.desktop`).
To disable it:

```bash
rm ~/.config/autostart/ip-rotator.desktop
```

## 2️⃣ Linux (Fedora, Rocky, CentOS, RHEL, openSUSE, Arch, etc.)

Most of these distributions also ship with NetworkManager pre‑installed.
The only difference is the package manager.

### Fedora / RHEL / CentOS / Rocky

```bash
# NetworkManager is usually already installed; if not:
sudo dnf install -y NetworkManager

# Start & enable NetworkManager (if it isn’t running already)
sudo systemctl start NetworkManager
sudo systemctl enable NetworkManager
```

### openSUSE

```bash
sudo zypper install -y NetworkManager
sudo systemctl start NetworkManager
sudo systemctl enable NetworkManager
```

### Arch Linux / Manjaro

```bash
sudo pacman -S networkmanager
sudo systemctl start NetworkManager
sudo systemctl enable NetworkManager
```

After NetworkManager is running, follow the **same import and run steps** as in the
Ubuntu/Debian/Mint section above.

## 3️⃣ Windows

The ip‑rotator **does not run natively on Windows** because it depends on
`nmcli`, which is part of NetworkManager – a Linux networking stack.

### Option A – Use WSL 2 (recommended)

1. **Install WSL 2** on Windows:

   ```powershell
   # As Administrator (PowerShell)
   wsl --install -d Ubuntu
   ```

2. **Open the Ubuntu terminal** from the Start menu.

3. **Follow the Linux (Ubuntu) instructions** exactly as shown in section 1️⃣.
   All scripts (`ip_rotator.py`, `fetch_vpngate.py`, `import_profiles.py`) run
   identically under WSL 2.

### Option B – Use OpenVPN GUI (manual)

1. **Install OpenVPN GUI** for Windows from <https://openvpn.net/community-downloads/>.

2. **Download/OpenVPN config files** (.ovpn or .wg) from your VPN provider.

3. Place them in a folder and import them via the OpenVPN GUI.

4. **Rotate manually** using the OpenVPN system tray icon, or script the
   `openvpn` CLI if you need automation.

*You will not be able to use the provided `import_profiles.py` or `nmcli` commands on native Windows.*

### Option C – Proton VPN CLI (if you have a Plus plan)

```powershell
# Install the official Proton VPN CLI (requires PowerShell as Admin)
iex ((Invoke-WebRequest -Uri https://protonvpn.com/download/cli).Content)

protonvpn signin          # enter your Proton email/password
protonvpn connect --country NL   # connect to a server
protonvpn disconnect
```

The rotator can be configured to use the Proton CLI (`protonvpn_cli: "protonvpn"`),
but the free plan does not allow random/country‑based selection (see the README).

## 4️⃣ Quick sanity check – is `nmcli` available?

Run this command in your terminal (Linux) or WSL:

```bash
which nmcli
```

- If it prints a path (e.g., `/usr/bin/nmcli`), you are good to go.
- If “command not found”, install NetworkManager per your distro’s instructions
  (see the sections above).

## 📦 Full command summary (one‑liner for each OS)

| OS                     | Install deps                                      | Import profiles                                 | Run daemon                                  |
|------------------------|---------------------------------------------------|--------------------------------------------------|---------------------------------------------|
| **Ubuntu / Mint / Debian** | `sudo apt update && sudo apt install -y python3 git` | `python3 import_profiles.py` | `python3 ip_rotator.py --daemon` |
| **Fedora / RHEL / CentOS** | `sudo dnf install -y NetworkManager` (then `systemctl start/enable`) | same as above | same as above |
| **Windows (WSL 2)**    | Inside Ubuntu: `sudo apt update && sudo apt install -y python3 git` | same as above | same as above |
| **Windows (native)**   | Install OpenVPN GUI or Proton VPN CLI manually | N/A (manual) | N/A (manual) |

## 📄 Need help?

- Check the original **README.md** for detailed per‑profile setup steps.
- Run `python3 ~/ip-rotator/ip_rotator.py --status` to verify your public IP.
- All logs are written to `~/ip-rotator/rotator.log`.