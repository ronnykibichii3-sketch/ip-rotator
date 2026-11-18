# IP Rotator – Windows Guide (using WSL 2)

The **code files** in this folder are identical to the original `/home/ronny/ip-rotator`; nothing has been modified there.

## How to get the rotator running on Windows

The ip‑rotator relies on `nmcli` (NetworkManager), which does not exist on native Windows.
The supported way to use it on Windows is **WSL 2** (Windows Subsystem for Linux).

### 1. Install WSL 2

Open PowerShell **as Administrator** and run:

```powershell
wsl --install -d Ubuntu
```

Restart your computer when prompted.

### 2. Open the Ubuntu terminal

- From the Start menu open **Ubuntu**.
- You will see a Bash prompt (`user@PC:~$`).

### 3. Copy or clone the ip‑rotator files inside WSL

If you have not already copied the folder, you can do it from within the Ubuntu terminal:

```bash
# From the Ubuntu terminal
git clone https://github.com/your-repo/ip-rotator.git ~/ip-rotator
# or, if you already have the files somewhere else:
cp -r /path/on/windows/Copy ~/ip-rotator
```

The folder `~/ip-rotator` now contains the same Python scripts you already have.

### 4. Install dependencies (Ubuntu inside WSL)

```bash
sudo apt update
sudo apt install -y python3 git
```

### 5. Import VPN profiles

Choose one of the methods from the main README (Proton VPN, VPN Gate, or any provider).  
All the import commands work exactly the same as on a native Linux box:

```bash
python3 ~/ip-rotator/import_profiles.py
```

### 6. Run the rotator

```bash
# Start the daemon (you will be asked for a password the first time)
python3 ~/ip-rotator/ip_rotator.py --daemon

# Or rotate once and exit
python3 ~/ip-rotator/ip_rotator.py --once

# Check your public IP
python3 ~/ip-rotator/ip_rotator.py --status
```

### 7. (Optional) Autostart

A desktop entry is already included in the original repo (`~/.config/autostart/ip-rotator.desktop`).
If you want it to start when you log into the Ubuntu session, ensure the file exists;
otherwise remove it:

```bash
rm ~/.config/autostart/ip-rotator.desktop
```

### 8. Stopping the daemon

```bash
python3 ~/ip-rotator/ip_rotator.py --stop
```

## Quick checklist (run inside WSL)

| Step | Command (Ubuntu/WLS) |
|------|----------------------|
| Install WSL 2 | `wsl --install -d Ubuntu` (PowerShell Admin) |
| Update packages | `sudo apt update && sudo apt install -y python3 git` |
| Import profiles | `python3 ~/ip-rotator/import_profiles.py` |
| Start daemon | `python3 ~/ip-rotator/ip_rotator.py --daemon` |
| Stop daemon | `python3 ~/ip-rotator/ip_rotator.py --stop` |

### If you really need a native‑Windows solution (no WSL)

- Use the **OpenVPN GUI** and rotate manually, or
- Use the **Proton VPN CLI** (requires a Plus plan) and configure the rotator to use `protonvpn_cli: "protonvpn"`,
  but random/country selection will be limited on the free plan.

*Do not modify any files inside the original `/home/ronny/ip-rotator` folder.* This guide only adds a new folder and instructions for Windows users via WSL 2.