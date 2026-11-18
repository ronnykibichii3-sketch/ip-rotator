#!/usr/bin/env python3
"""
ip_rotator.py - a transparent, password-gated IP rotation helper.

What it does:
  * On login it asks for a password (KDE/zenity dialog).
  * If the password is correct it rotates the active VPN connection
    between the NetworkManager profiles listed in config.json.
  * It logs every change and shows a desktop notification.

What it does NOT do:
  * Store your VPN account password (log in once in the Proton app).
  * Hide itself, obfuscate, or read credentials.
  * Rotate "every second" - that is technically impossible (see README).

Run:
  python3 ip_rotator.py --set-password     # change the access password
  python3 ip_rotator.py --status           # show current public IP
  python3 ip_rotator.py --once             # rotate one step, then exit
  python3 ip_rotator.py --daemon           # normal background mode
  python3 ip_rotator.py --stop             # ask a running daemon to stop
"""

import argparse
import base64
import getpass
import hashlib
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG = BASE / "config.json"
LOG = BASE / "rotator.log"
PIDFILE = BASE / "rotator.pid"
STOPFILE = BASE / "STOP"

# Do not rotate faster than this even if config asks for less.
MIN_INTERVAL = 30
IP_ECHO = "https://api.ipify.org"


# --------------------------------------------------------------------------
# config / password
# --------------------------------------------------------------------------
def load_config() -> dict:
    if not CONFIG.exists():
        return {}
    with CONFIG.open(encoding="utf-8") as fh:
        return json.load(fh)


def save_config(cfg: dict) -> None:
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    os.chmod(CONFIG, 0o600)


def hash_password(password: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return base64.b64encode(dk).decode()


def set_password(password: str | None = None) -> None:
    cfg = load_config()
    if password is None:
        password = ask_password("Choose a new access password")
        again = ask_password("Repeat the password")
        if password != again:
            print("Passwords do not match.")
            sys.exit(1)
    if not password:
        print("Empty password refused.")
        sys.exit(1)
    salt = os.urandom(16)
    cfg["salt"] = base64.b64encode(salt).decode()
    cfg["password_hash"] = hash_password(password, salt)
    save_config(cfg)
    print("Password saved to", CONFIG)


def check_password(cfg: dict) -> bool:
    want = cfg.get("password_hash")
    salt_b64 = cfg.get("salt")
    if not want or not salt_b64:
        print("No password configured. Run: ip_rotator.py --set-password")
        return False
    entered = ask_password("IP Rotator - enter access password")
    if entered is None:
        return False
    got = hash_password(entered, base64.b64decode(salt_b64))
    return got == want


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def ask_password(prompt: str) -> str | None:
    """Graphical password prompt when a desktop is available, else terminal."""
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        for cmd in (
            ["kdialog", "--password", prompt],
            ["zenity", "--password", "--title", prompt],
        ):
            if shutil.which(cmd[0]):
                r = subprocess.run(cmd, capture_output=True, text=True)
                if r.returncode == 0:
                    return r.stdout.rstrip("\n")
                return None
    try:
        return getpass.getpass(prompt + ": ")
    except (EOFError, KeyboardInterrupt):
        return None


def notify(title: str, body: str) -> None:
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", title, body], check=False)


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def public_ip() -> str:
    if not shutil.which("curl"):
        return "unknown"
    r = subprocess.run(
        ["curl", "-sS", "--max-time", "8", IP_ECHO],
        capture_output=True, text=True, check=False,
    )
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "unknown"


def nmcli(*args: str, timeout: int = 45) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["nmcli", *args], capture_output=True, text=True,
        timeout=timeout, check=False,
    )


# --------------------------------------------------------------------------
# rotation backends
# --------------------------------------------------------------------------
def rotate_nmcli(cfg: dict, index: int) -> int:
    """Bring up the next NetworkManager profile, drop the previous one.

    Tries up to three profiles per cycle so one dead server does not leave the
    machine without a tunnel for a whole interval.
    """
    profiles = cfg.get("profiles") or []
    if not profiles:
        raise RuntimeError(
            "No VPN profiles configured. Add WireGuard/OpenVPN profile names "
            "to config.json -> 'profiles' (see README)."
        )

    current = cfg.get("_current")
    if cfg.get("random_profiles") and len(profiles) > 1:
        rest = [p for p in profiles if p != current]
        random.shuffle(rest)
        order = rest
    else:
        start = index % len(profiles)
        order = profiles[start:] + profiles[:start]

    last_error = "no candidates"
    for target in order[:3]:
        if current and current != target:
            nmcli("connection", "down", current, timeout=15)

        log(f"connecting profile: {target}")
        try:
            r = nmcli("connection", "up", target, timeout=45)
        except subprocess.TimeoutExpired:
            log(f"{target}: timed out, skipping")
            nmcli("connection", "down", target, timeout=15)
            last_error = f"{target}: timeout"
            current = None
            continue

        if r.returncode == 0:
            cfg["_current"] = target
            return index + 1

        last_error = f"{target}: {(r.stderr or r.stdout).strip()[:160]}"
        log(f"failed to bring up {last_error}")
        nmcli("connection", "down", target, timeout=15)
        current = None

    raise RuntimeError(f"no profile could be brought up (last error: {last_error})")


def _proton_cli(cfg: dict) -> str | None:
    """Official binary is 'protonvpn'; accept the legacy name as fallback."""
    for name in (cfg.get("protonvpn_cli", "protonvpn"), "protonvpn", "protonvpn-cli"):
        path = shutil.which(name)
        if path:
            return path
    return None


class PlanRestriction(RuntimeError):
    """The Proton plan does not allow the requested server selection."""


def rotate_proton_cli(cfg: dict, index: int) -> int:
    """Rotate using the official Proton VPN Linux CLI (protonvpn).

    Selection strategy comes from cfg["proton_selection"]:
      "random"  -> protonvpn connect --random        (paid plans only)
      "country" -> protonvpn connect --country <code> (cycles proton_servers)
    """
    cli = _proton_cli(cfg)
    if not cli:
        raise RuntimeError("Proton VPN CLI not installed and no nmcli profiles set.")

    strategy = cfg.get("proton_selection", "random")
    if strategy == "country":
        servers = cfg.get("proton_servers") or []
        if not servers:
            raise RuntimeError("config.json -> 'proton_servers' is empty.")
        target = servers[index % len(servers)]
        args = ["connect", "--country", target]
        label = target
    else:
        args = ["connect", "--random"]
        label = "random"

    subprocess.run([cli, "disconnect"], capture_output=True, check=False)
    time.sleep(2)
    log(f"protonvpn {' '.join(args)}")
    r = subprocess.run(
        [cli, *args], capture_output=True, text=True, check=False, timeout=120,
    )
    out = (r.stdout + r.stderr).strip()
    low = out.lower()

    if "free plan" in low:
        raise PlanRestriction(
            "Proton free plan blocks location/random selection. "
            "Random rotation needs Proton VPN Plus. "
            "Use plain 'protonvpn connect' for a stable free connection."
        )
    if r.returncode != 0 or "error:" in low:
        raise RuntimeError(f"connect failed ({label}): {out[:300]}")

    first = next((ln.strip() for ln in out.splitlines() if ln.strip()), f"connected ({label})")
    log(f"connected: {first}")
    return index + 1


def do_rotation(cfg: dict, index: int) -> int:
    if cfg.get("profiles"):
        return rotate_nmcli(cfg, index)
    return rotate_proton_cli(cfg, index)


# --------------------------------------------------------------------------
# daemon
# --------------------------------------------------------------------------
def running_pid() -> int | None:
    if not PIDFILE.exists():
        return None
    try:
        pid = int(PIDFILE.read_text().strip())
    except ValueError:
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


def daemon(cfg: dict) -> None:
    pid = running_pid()
    if pid:
        print(f"Already running (pid {pid}).")
        return

    if not check_password(cfg):
        log("access denied - wrong password")
        notify("IP Rotator", "Access denied")
        return

    if not cfg.get("profiles"):
        cli = shutil.which(cfg.get("protonvpn_cli", "protonvpn-cli"))
        if not cli or not cfg.get("proton_servers"):
            log("nothing to rotate: add NetworkManager profiles or proton_servers "
                "to config.json (see README).")
            notify("IP Rotator", "No VPN profiles configured")
            return

    PIDFILE.write_text(str(os.getpid()))
    STOPFILE.unlink(missing_ok=True)

    interval = max(int(cfg.get("interval_seconds", 300)), MIN_INTERVAL)
    log(f"started (pid {os.getpid()}), interval {interval}s")
    notify("IP Rotator", f"Running - rotating every {interval}s")

    stop = {"flag": False}

    def _stop(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    index = 0
    try:
        while not stop["flag"] and not STOPFILE.exists():
            try:
                index = do_rotation(cfg, index)
                save_config(cfg)
                time.sleep(6)
                ip = public_ip()
                log(f"public IP now: {ip}")
                notify("IP Rotator", f"IP changed to {ip}")
            except PlanRestriction as exc:
                # Pointless to retry: the plan will not change mid-run.
                log(f"stopping rotation: {exc}")
                notify("IP Rotator", str(exc)[:180])
                break
            except Exception as exc:  # noqa: BLE001 - keep the daemon alive
                log(f"rotation error: {exc}")
                notify("IP Rotator", f"Error: {exc}")

            waited = 0
            while waited < interval and not stop["flag"] and not STOPFILE.exists():
                time.sleep(1)
                waited += 1
    finally:
        PIDFILE.unlink(missing_ok=True)
        STOPFILE.unlink(missing_ok=True)
        log("stopped")


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Password-gated IP rotation helper")
    ap.add_argument("--daemon", action="store_true", help="run the rotation loop")
    ap.add_argument("--once", action="store_true", help="rotate one step and exit")
    ap.add_argument("--status", action="store_true", help="print current public IP")
    ap.add_argument("--set-password", action="store_true", help="change access password")
    ap.add_argument("--stop", action="store_true", help="stop a running daemon")
    args = ap.parse_args()

    cfg = load_config()

    if args.set_password:
        set_password()
    elif args.status:
        print("public IP:", public_ip())
    elif args.stop:
        STOPFILE.write_text("stop")
        print("Stop requested.")
    elif args.once:
        if not check_password(cfg):
            print("Access denied.")
            return
        do_rotation(cfg, 0)
        save_config(cfg)
        print("public IP:", public_ip())
    elif args.daemon:
        daemon(cfg)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
