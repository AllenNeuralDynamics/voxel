"""s5cmd-backed file upload to S3.

`run_s5cmd` moves a group of files via one parallel ``s5cmd run`` -- pure mechanism, no
queue, threads, or state. Orchestration (queuing, backpressure, eviction) lives in the
caller (the writer), which is the pipeline owner.

The `S3Store` selects the connection: its endpoint and credential profile are passed as
``--endpoint-url`` / ``--profile`` flags and its region via a subprocess-scoped ``AWS_REGION``
(so concurrent uploads to different stores can't clash). Credentials themselves come from the
AWS chain (the profile, an instance role, or ambient env). The binary ships with the `s5cmd`
dependency.
"""

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from functools import cache
from importlib.metadata import distribution
from pathlib import Path

from cloudpathlib import S3Path
from vxlib import AnonymousCredentials, ProfileCredentials, S3Store


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


def run_s5cmd(jobs: list[TransferJob], store: S3Store | None, *, numworkers: int, retry_count: int) -> int:
    """Upload one group via a single ``s5cmd run``, reaching S3 via `store` (an empty/``None``
    store falls back to the ambient AWS environment); returns total bytes moved. Raises
    `TransferError` if s5cmd exits non-zero. Blocks until the group is durable in S3."""
    if not jobs:
        return 0
    total_bytes = sum(j.src.stat().st_size for j in jobs if j.src.exists())
    script = "\n".join(f"cp {shlex.quote(str(j.src))} {shlex.quote(str(j.dest))}" for j in jobs)
    creds = store.credentials if store else None
    connection = [
        *(["--endpoint-url", store.endpoint] if store and store.endpoint else []),
        *(["--profile", creds.name] if isinstance(creds, ProfileCredentials) else []),
        *(["--no-sign-request"] if isinstance(creds, AnonymousCredentials) else []),
    ]
    args = [
        s5cmd_binary(),
        "--json",
        *connection,
        "--numworkers",
        str(numworkers),
        "--retry-count",
        str(retry_count),
        "run",
    ]
    env = os.environ | ({"AWS_REGION": store.region} if store and store.region else {})
    proc = subprocess.run(args, input=script, capture_output=True, text=True, check=False, env=env)
    if proc.returncode != 0:
        raise TransferError(f"upload failed:\n{proc.stderr or proc.stdout}")
    return total_bytes
