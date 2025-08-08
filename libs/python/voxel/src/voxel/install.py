# src/voxel/install.py

import os
import sys
import subprocess

EXTRA_TO_WHEELS = {
    "etl-opto": ["optoICC", "optoKummenberg"],
    "egrabber": ["egrabber"],
}


def install_optional_wheels():
    # Try to detect extras passed via pip
    requested_extras = set()
    for arg in sys.argv:
        if "[" in arg:
            extras_part = arg.split("[", 1)[1].split("]")[0]
            requested_extras.update(e.strip() for e in extras_part.split(","))

    # Install relevant wheels
    wheels_dir = os.path.join(os.path.dirname(__file__), ".wheels")
    if not os.path.exists(wheels_dir):
        return

    for extra, prefixes in EXTRA_TO_WHEELS.items():
        if extra in requested_extras:
            for prefix in prefixes:
                matches = [f for f in os.listdir(wheels_dir) if f.startswith(prefix) and f.endswith(".whl")]
                for fname in matches:
                    full_path = os.path.abspath(os.path.join(wheels_dir, fname))
                    print(f"[voxel] Installing optional wheel: {fname}")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", full_path])


if __name__ == "__main__":
    install_optional_wheels()
