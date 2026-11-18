#!/usr/bin/env python3
"""
fetch_vpngate.py - download free OpenVPN configs from the public VPN Gate
                   directory (vpngate.net, University of Tsukuba project).

No account, no signup, many countries. The configs are written to
./profiles/ as .ovpn files; import them with import_profiles.py.

SECURITY WARNING
    VPN Gate servers are run by volunteers. The operator can see and modify
    your traffic. Use them for geo-testing or throwaway browsing only - never
    for banking, work logins, or anything you would not do on public Wi-Fi.
    For real privacy use a paid provider (Mullvad, IVPN, Proton Plus).

Usage:
    python3 fetch_vpngate.py                 # 6 servers, 6 countries
    python3 fetch_vpngate.py --count 10
    python3 fetch_vpngate.py --countries US,JP,GB --count 3
    python3 fetch_vpngate.py --list          # just show what is available
"""

import argparse
import base64
import json
import random
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "profiles"
API = "https://www.vpngate.net/api/iphone/"

# Countries that are generally safe to route through for testing.
DEFAULT_ALLOW = [
    "US", "CA", "GB", "DE", "NL", "FR", "CH", "SE", "NO", "FI", "DK",
    "IE", "AT", "BE", "IT", "ES", "PT", "PL", "CZ", "RO", "JP", "KR",
    "SG", "AU", "MX", "PH", "ID", "TH", "VN",
]
EXCLUDED = {"RU", "MM", "IR", "CN", "TR", "BY", "SY", "KP"}


def fetch_csv() -> str:
    req = urllib.request.Request(API, headers={"User-Agent": "ip-rotator/1.0"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read().decode("utf-8", "replace")


def parse(csv_text: str) -> list[dict]:
    servers = []
    for line in csv_text.splitlines():
        if not line or line.startswith(("*", "#")):
            continue
        parts = line.split(",")
        if len(parts) < 15:
            continue
        try:
            score = int(parts[2])
            speed = int(parts[4])
        except ValueError:
            continue
        servers.append(
            {
                "host": parts[0],
                "ip": parts[1],
                "score": score,
                "ping": parts[3],
                "speed_mbps": round(speed / 1_000_000, 1),
                "country": parts[5],
                "cc": parts[6],
                "sessions": parts[7],
                "config_b64": parts[14],
            }
        )
    return servers


def pick(servers: list[dict], count: int, allowed: set[str]) -> list[dict]:
    """Best server per country first, so the rotation changes countries."""
    by_cc: dict[str, list[dict]] = defaultdict(list)
    for s in servers:
        if s["cc"] in allowed and s["config_b64"].strip():
            by_cc[s["cc"]].append(s)

    for cc in by_cc:
        by_cc[cc].sort(key=lambda s: s["score"], reverse=True)

    chosen: list[dict] = []
    # round 1: one per country, strongest first
    for cc in sorted(by_cc, key=lambda c: by_cc[c][0]["score"], reverse=True):
        if len(chosen) >= count:
            break
        chosen.append(by_cc[cc][0])
    # round 2: second server per country if we still need more
    for cc in by_cc:
        if len(chosen) >= count:
            break
        if len(by_cc[cc]) > 1:
            chosen.append(by_cc[cc][1])

    random.shuffle(chosen)
    return chosen[:count]


def write_configs(servers: list[dict], out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for s in servers:
        try:
            body = base64.b64decode(s["config_b64"]).decode("utf-8", "replace")
        except Exception:
            continue
        if "remote " not in body:
            continue
        name = f"{s['cc'].lower()}-{s['host']}.ovpn"
        path = out / name
        header = (
            f"# VPN Gate volunteer server: {s['country']} ({s['cc']})\n"
            f"# host={s['host']} ip={s['ip']} speed={s['speed_mbps']}Mbps "
            f"score={s['score']} sessions={s['sessions']}\n"
            "# UNTRUSTED OPERATOR - test/geo use only, no logins or banking.\n"
        )
        path.write_text(header + body, encoding="utf-8")
        path.chmod(0o600)
        written.append(path)
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description="Download free VPN Gate OpenVPN configs")
    ap.add_argument("--count", type=int, default=6)
    ap.add_argument("--countries", help="comma separated codes, e.g. US,JP,GB")
    ap.add_argument("--min-speed", type=float, default=1.0, help="minimum Mbps")
    ap.add_argument("--list", action="store_true", help="list availability, write nothing")
    args = ap.parse_args()

    if args.countries:
        allowed = {c.strip().upper() for c in args.countries.split(",") if c.strip()}
    else:
        allowed = set(DEFAULT_ALLOW)

    print("Fetching VPN Gate directory ...")
    try:
        servers = parse(fetch_csv())
    except Exception as exc:  # noqa: BLE001
        print(f"Download failed: {exc}")
        sys.exit(1)

    servers = [s for s in servers if s["cc"] not in EXCLUDED and s["speed_mbps"] >= args.min_speed]
    print(f"{len(servers)} usable servers in {len({s['cc'] for s in servers})} countries")

    if args.list:
        counts: dict[tuple[str, str], int] = defaultdict(int)
        for s in servers:
            counts[(s["cc"], s["country"])] += 1
        for (cc, country), n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {cc}  {country:24s} {n:3d} servers")
        return

    chosen = pick(servers, args.count, allowed)
    if not chosen:
        print("No usable servers for that country filter.")
        sys.exit(1)

    written = write_configs(chosen, OUT)
    if not written:
        print("No configs could be decoded.")
        sys.exit(1)

    print(f"\nWrote {len(written)} configs to {OUT}:")
    for path in written:
        print("  -", path.name)

    print("\nSECURITY REMINDER: these are volunteer-run servers.")
    print("Do not log into accounts or do banking through them.")
    print("\nNext step:")
    print("  python3 import_profiles.py --dry-run")
    print("  python3 import_profiles.py        # needs sudo")


if __name__ == "__main__":
    main()
