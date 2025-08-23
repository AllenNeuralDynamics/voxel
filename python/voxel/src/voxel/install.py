# src/voxel/install.py

import subprocess
import sys
from pathlib import Path

EXTRA_TO_WHEELS = {
    'etl-opto': ['optoICC', 'optoKummenberg'],
    'egrabber': ['egrabber'],
}


def install_optional_wheels():
    # Try to detect extras passed via pip
    requested_extras = set()
    for arg in sys.argv:
        if '[' in arg:
            extras_part = arg.split('[', 1)[1].split(']')[0]
            requested_extras.update(e.strip() for e in extras_part.split(','))

    # Install relevant wheels
    wheels_dir = Path(__file__).parent / '.wheels'
    if not wheels_dir.exists():
        return

    for extra, prefixes in EXTRA_TO_WHEELS.items():
        if extra in requested_extras:
            for prefix in prefixes:
                matches = [f for f in wheels_dir.iterdir() if f.name.startswith(prefix) and f.name.endswith('.whl')]
                for fname in matches:
                    full_path = (wheels_dir / fname).resolve()
                    print(f'[voxel] Installing optional wheel: {fname.name}')
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', str(full_path)])


if __name__ == '__main__':
    install_optional_wheels()
