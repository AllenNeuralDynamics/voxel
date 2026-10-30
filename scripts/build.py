"""Build the web frontend before packaging Voxel."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
STATION = WEB / "station"


def _run(command: list[str], *, cwd: Path) -> None:
    executable = shutil.which(command[0])
    if executable is None:
        raise SystemExit(f"Required build command is not installed: {command[0]}")
    result = subprocess.run([executable, *command[1:]], cwd=cwd, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)


def main() -> None:
    _run(["vp", "install", "--frozen-lockfile"], cwd=WEB)
    _run(["vp", "build"], cwd=STATION)
    _run(["uv", "build", *sys.argv[1:]], cwd=ROOT)


if __name__ == "__main__":
    main()
