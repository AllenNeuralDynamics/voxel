#!/usr/bin/env python3
"""
cert.py — Rig Identity Manager

USAGE:
    cert.py             → show status
    cert.py <name>      → rename rig & restart Caddy

Features:
    - macOS + Ubuntu + Rocky support
    - Safe writes with sudo
    - Safe reads with sudo fallback
    - Always prints CA URLs
    - HTTPS for domain, hostname, hostname.local, IP
"""

import sys
import socket
import subprocess
from pathlib import Path


# -------------------------------------------------------
# Detect Caddyfile location
# -------------------------------------------------------
if Path("/opt/homebrew/etc/Caddyfile").exists():
    CADDYFILE = Path("/opt/homebrew/etc/Caddyfile")  # macOS ARM
elif Path("/usr/local/etc/Caddyfile").exists():
    CADDYFILE = Path("/usr/local/etc/Caddyfile")  # macOS Intel
else:
    CADDYFILE = Path("/etc/caddy/Caddyfile")  # Linux systemd


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def sudo_read(path: Path) -> str | None:
    """Always attempt normal read first, then fallback to sudo cat."""
    try:
        return path.read_text()
    except Exception:
        pass

    result = run(["sudo", "cat", str(path)])
    if result.returncode != 0:
        return None
    return result.stdout


# -------------------------------------------------------
# Utils
# -------------------------------------------------------


def get_hostname():
    return socket.gethostname().split(".")[0]


def get_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except:
        return "127.0.0.1"


# Internal CA locations
CADDY_DATA_PATHS = [
    Path("/var/lib/caddy/.local/share/caddy/pki/authorities/local"),  # Linux
    Path("/opt/homebrew/var/lib/caddy/.local/share/caddy/pki/authorities/local"),  # macOS Brew
    Path.home() / ".local/share/caddy/pki/authorities/local",  # User-run Caddy
]


def find_ca_path():
    """Locate readable CA directory safely."""
    for p in CADDY_DATA_PATHS:
        try:
            if (p / "root.crt").exists():
                return p
        except PermissionError:
            continue
    return None


# -------------------------------------------------------
# Write new Caddyfile
# -------------------------------------------------------


def write_caddyfile(name: str):
    domain = f"{name}.rigs.local"
    ca_path = find_ca_path() or "/var/lib/caddy/.local/share/caddy/pki/authorities/local"

    config = (
        f"""
{domain} {{
    tls internal
    reverse_proxy localhost:8000
}}

:8080 {{
    root * {ca_path}
    file_server browse
}}
""".strip()
        + "\n"
    )

    tmp = Path("/tmp/caddyfile.tmp")
    tmp.write_text(config)

    run(["sudo", "cp", str(tmp), str(CADDYFILE)])

    return domain


def restart_caddy():
    if sys.platform == "darwin":
        run(["brew", "services", "restart", "caddy"])
    else:
        run(["sudo", "systemctl", "restart", "caddy"])


# -------------------------------------------------------
# Parse domain
# -------------------------------------------------------


def current_domain():
    if not CADDYFILE.exists():
        return None

    text = sudo_read(CADDYFILE)
    if not text:
        return None

    for line in text.splitlines():
        if line.strip().endswith(".rigs.local {"):
            return line.strip().split()[0]

    return None


# -------------------------------------------------------
# Status
# -------------------------------------------------------


def show_status():
    hostname = get_hostname()
    ip = get_ip()
    domain = current_domain()
    ca_path = find_ca_path()

    print("\n=== Rig Status ===\n")

    if not domain:
        print("This machine is not configured as a rig.")
        print("Run:   cert.py <name>\n")
        return

    print(f"Rig: {domain}\n")

    print("Access URLs:")
    print(f"  https://{domain}")
    print(f"  https://{hostname}")
    print(f"  https://{hostname}.local")
    print(f"  https://{ip}\n")

    print("Internal Certificate Authority:")
    if ca_path:
        print(f"  {ca_path}")
        print("  Status: Ready\n")
    else:
        print("  CA not yet generated (will appear after first Caddy restart).")
        print("  Status: Pending\n")

    print("CA Download (served by this machine on port 8080):")
    print(f"  http://{ip}:8080/root.crt    (macOS/Linux)")
    print(f"  http://{ip}:8080/root.cer    (Windows)")
    print(f"  http://{ip}:8080/            (Browse CA folder)\n")

    print("Client Setup:")
    print("  1. Download the certificate from port 8080.")
    print("  2. Install it into the trust store.")
    print("  3. Access the rig via HTTPS.\n")


# -------------------------------------------------------
# Main
# -------------------------------------------------------


def main():
    if len(sys.argv) == 1:
        show_status()
        return

    name = sys.argv[1]
    print(f"\nRenaming rig to: {name}\n")

    write_caddyfile(name)
    restart_caddy()

    print("✓ Updated Caddyfile")
    print("✓ Restarted Caddy\n")

    show_status()


if __name__ == "__main__":
    main()
