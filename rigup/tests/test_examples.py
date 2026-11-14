import subprocess
import sys
from pathlib import Path

EXAMPLES = Path(__file__).parents[1] / "examples"


def test_the_simulated_rig_example_runs_to_the_end() -> None:
    done = subprocess.run(
        [sys.executable, "simulated_rig.py"], cwd=EXAMPLES, capture_output=True, text=True, timeout=60, check=False
    )

    assert done.returncode == 0, done.stderr
