"""s5cmd-backed file upload to S3.

`run_s5cmd` moves a group of files via one parallel ``s5cmd run`` -- pure mechanism, no
queue, threads, or state. Orchestration (queuing, backpressure, eviction) lives in the
caller (the writer), which is the pipeline owner.

s5cmd reads all S3 connection settings from the environment -- credentials / instance role,
region (`AWS_REGION`), endpoint (`S3_ENDPOINT_URL`, for MinIO et al.) -- so nothing here
carries connection config. The binary ships with the `s5cmd` dependency.
"""

import shlex
import shutil
import subprocess
from dataclasses import dataclass
from functools import cache
from importlib.metadata import distribution
from pathlib import Path

from cloudpathlib import S3Path


@cache
def s5cmd_binary() -> str:
    """Absolute path to the bundled s5cmd binary (the wheel ships it at
    ``s5cmd/bin/s5cmd`` -- skips the python console-script wrapper), with a PATH fallback."""
    for f in distribution("s5cmd").files or []:
        if str(f).replace("\\", "/").startswith("s5cmd/bin/s5cmd"):
            return str(Path(f.locate()).resolve())
    if found := shutil.which("s5cmd"):
        return found
    raise FileNotFoundError("s5cmd binary not found -- is the 's5cmd' package installed?")


@dataclass(frozen=True, slots=True)
class TransferJob:
    """One file to move: local ``src`` -> remote ``dest``."""

    src: Path
    dest: S3Path


class TransferError(RuntimeError):
    """An s5cmd upload failed (after its per-object retries)."""


def run_s5cmd(jobs: list[TransferJob], *, numworkers: int, retry_count: int) -> int:
    """Upload one group via a single ``s5cmd run``; returns total bytes moved. Raises
    `TransferError` if s5cmd exits non-zero. Blocks until the group is durable in S3."""
    if not jobs:
        return 0
    total_bytes = sum(j.src.stat().st_size for j in jobs if j.src.exists())
    script = "\n".join(f"cp {shlex.quote(str(j.src))} {shlex.quote(str(j.dest))}" for j in jobs)
    args = [s5cmd_binary(), "--json", "--numworkers", str(numworkers), "--retry-count", str(retry_count), "run"]
    proc = subprocess.run(args, input=script, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise TransferError(f"upload failed:\n{proc.stderr or proc.stdout}")
    return total_bytes
