#!/usr/bin/env python3
"""
import_profiles.py - import WireGuard/OpenVPN configs into NetworkManager
                     and register them with ip_rotator.

This is the piece that turns "a folder of .conf/.ovpn files" into
rotatable NetworkManager connections for ip_rotator.py.

It never stores credentials. It uses `nmcli connection import`, which needs
root (sudo will ask for your password).

Usage:
    python3 import_profiles.py                     # import ./profiles/*.{conf,ovpn}
    python3 import_profiles.py --dir ~/Downloads   # import from another folder
    python3 import_profiles.py --dry-run           # show what would happen
    python3 import_profiles.py --list              # show imported + configured
    python3 import_profiles.py --remove            # delete the ipr-* connections
    python3 import_profiles.py --no-register       # import but do not touch config.json
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG = BASE / "config.json"
DEFAULT_DIR = BASE / "profiles"

KIND_BY_SUFFIX = {".conf": "wireguard", ".ovpn": "openvpn"}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def nmcli(*args: str) -> subprocess.CompletedProcess:
    return run(["nmcli", *args])


def sudo_nmcli(*args: str) -> subprocess.CompletedProcess:
    return run(["sudo", "nmcli", *args])


def privileged(*args: str) -> subprocess.CompletedProcess:
    """Try nmcli as the user (polkit) and fall back to sudo only if refused."""
    r = nmcli(*args)
    if r.returncode == 0:
        return r
    text = (r.stderr + r.stdout).lower()
    if any(s in text for s in ("insufficient privileges", "not authorized",
                               "permission denied", "access denied", "polkit")):
        return sudo_nmcli(*args)
    return r


def load_config() -> dict:
    if not CONFIG.exists():
        return {}
    with CONFIG.open(encoding="utf-8") as fh:
        return json.load(fh)


def save_config(cfg: dict) -> None:
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    os.chmod(CONFIG, 0o600)


def slug(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._")
    return text[:40] or "vpn"


def existing_uuids() -> set[str]:
    r = nmcli("-t", "-f", "UUID", "connection", "show")
    return {ln.strip() for ln in r.stdout.splitlines() if ln.strip()}


def existing_ids() -> list[str]:
    r = nmcli("-t", "-f", "NAME", "connection", "show")
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def configured_profiles() -> list[str]:
    return [str(p) for p in (load_config().get("profiles") or [])]


# --------------------------------------------------------------------------
# import / remove
# --------------------------------------------------------------------------
def import_one(path: Path, prefix: str, dry_run: bool) -> tuple[bool, str, str]:
    """Return (ok, connection_id, message)."""
    kind = KIND_BY_SUFFIX[path.suffix.lower()]
    target_id = f"{prefix}-{slug(path.stem)}"

    if dry_run:
        return True, target_id, f"would import as [{kind}] id={target_id}"

    before = existing_uuids()

    r = privileged("connection", "import", "type", kind, "file", str(path))
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().replace("\n", " ")[:300]
        return False, target_id, f"import failed: {msg}"

    match = re.search(r"\(([0-9a-f-]{36})\)", r.stdout)
    new_uuid = match.group(1) if match else None
    if not new_uuid:
        added = existing_uuids() - before
        new_uuid = added.pop() if len(added) == 1 else None
    if not new_uuid:
        return False, target_id, "import seemed to work but no new UUID was found"

    # Rename for stable rotation order and stop NM from connecting it at boot.
    r2 = privileged(
        "connection", "modify", new_uuid,
        "connection.id", target_id,
        "connection.autoconnect", "no",
    )
    if r2.returncode != 0:
        msg = (r2.stderr or r2.stdout).strip()[:300]
        return False, target_id, f"imported but rename failed: {msg}"

    return True, target_id, "imported"


def cmd_import(directory: Path, prefix: str, dry_run: bool, register: bool) -> int:
    files = sorted(
        p for p in directory.glob("*") if p.suffix.lower() in KIND_BY_SUFFIX
    )
    if not files:
        print(f"No .conf/.ovpn files in {directory}")
        print("Drop configs there first (see README 'Setup C').")
        return 1

    ids: list[str] = []
    failures = 0
    for path in files:
        ok, cid, message = import_one(path, prefix, dry_run)
        print(f"[{'ok ' if ok else 'ERR'}] {path.name:38s} {message}")
        if ok:
            ids.append(cid)
        else:
            failures += 1

    if register and ids and not dry_run:
        cfg = load_config()
        merged = list(dict.fromkeys([*cfg.get("profiles", []), *ids]))
        cfg["profiles"] = merged
        cfg.pop("_current", None)
        save_config(cfg)
        print(f"\nconfig.json now rotates {len(merged)} profile(s):")
        for name in merged:
            print("  -", name)

    if dry_run:
        print("\ndry run: nothing was imported and config.json was not changed")

    return 0 if failures == 0 else 2


def cmd_remove(prefix: str) -> int:
    ids = [i for i in existing_ids() if i.startswith(prefix + "-")]
    if not ids:
        print(f"No connections named '{prefix}-*'.")
        return 0
    for cid in ids:
        r = privileged("connection", "delete", cid)
        print(f"[{'ok ' if r.returncode == 0 else 'ERR'}] delete {cid}")

    cfg = load_config()
    cfg["profiles"] = [p for p in cfg.get("profiles", []) if not p.startswith(prefix + "-")]
    cfg.pop("_current", None)
    save_config(cfg)
    print("config.json cleaned up.")
    return 0


def cmd_list(prefix: str) -> int:
    have = set(existing_ids())
    configured = configured_profiles()
    print("Imported connections (ip_rotator order):")
    if not configured:
        print("  (none configured)")
    for i, name in enumerate(configured, 1):
        state = "present" if name in have else "MISSING"
        print(f"  {i:2d}. {name:40s} [{state}]")

    others = sorted(n for n in have if n.startswith(prefix + "-") and n not in configured)
    if others:
        print("\nImported but not in config.json:")
        for name in others:
            print("   -", name)

    print("\nCurrent connection state:")
    r = nmcli("-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active")
    for line in r.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and ("wireguard" in parts[1] or "vpn" in parts[1]):
            print(f"   {parts[0]}  ({parts[1]}) on {parts[2]}")
    return 0


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Import VPN configs into NetworkManager")
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="folder with .conf/.ovpn files")
    ap.add_argument("--prefix", default="ipr", help="connection id prefix (default: ipr)")
    ap.add_argument("--dry-run", action="store_true", help="show actions, change nothing")
    ap.add_argument("--no-register", action="store_true", help="do not update config.json")
    ap.add_argument("--list", action="store_true", help="show imported/configured profiles")
    ap.add_argument("--remove", action="store_true", help="delete ipr-* connections")
    args = ap.parse_args()

    if args.list:
        sys.exit(cmd_list(args.prefix))
    if args.remove:
        sys.exit(cmd_remove(args.prefix))

    if not args.dir.is_dir():
        print(f"Not a directory: {args.dir}")
        sys.exit(1)

    sys.exit(cmd_import(args.dir, args.prefix, args.dry_run, not args.no_register))


if __name__ == "__main__":
    main()
