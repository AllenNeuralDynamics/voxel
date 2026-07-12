"""Generic benchmark harness: provenance capture + a versioned, append-only JSONL results sink.

A bench supplies two pydantic models per measured data point -- a ``run`` (the independent variables:
settings and environment) and a ``result`` (the raw measurements) -- and calls ``Results.append(run,
result)``. The harness wraps each with an envelope carrying the schema version, a ``run_id`` shared across
one invocation's records, a timestamp, git commit/dirty, machine identity, and library versions, then
appends one JSON line.

Design rules this enforces:
- Store raw observations only; derive metrics (fps, MB/s, ratios) in analysis, never here.
- Every record is self-contained (provenance + settings + measurements) so analysis is filter/group, not
  joins across files.
- Append-only and schema-versioned, so old records stay readable as the ``run``/``result`` shape evolves.

Reusability is the point: a new bench reuses this file verbatim and only defines its own ``run``/``result``
pydantic models plus the package list whose versions it wants recorded.
"""

import os
import platform
import subprocess
from datetime import UTC, datetime
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import psutil
from pydantic import BaseModel

SCHEMA_VERSION = 1


class GitInfo(BaseModel):
    commit: str | None  # short SHA of HEAD, or None if not a git checkout
    dirty: bool | None  # True if the working tree has uncommitted changes (None if unknown)


class MachineInfo(BaseModel):
    host: str
    cpu_count: int | None  # logical processors
    ram_gb: float | None  # total physical RAM (machine identity, not the run's working set)
    platform: str


class Provenance(BaseModel):
    git: GitInfo
    machine: MachineInfo
    versions: dict[str, str | None]  # package -> installed version (None if not installed)


class Envelope(BaseModel):
    """One appended record: provenance + the bench's own ``run``/``result`` payloads."""

    schema_version: int = SCHEMA_VERSION
    bench: str  # which benchmark produced this (one JSONL file per bench, but recorded for safety)
    run_id: str  # shared across all records from one invocation, so combos can be grouped
    ts: str  # ISO-8601 UTC
    git: GitInfo
    machine: MachineInfo
    versions: dict[str, str | None]
    run: dict[str, Any]  # the bench's run model, dumped
    result: dict[str, Any]  # the bench's result model, dumped


def _sh(*args: str) -> str | None:
    """Run a command in the repo dir and return stripped stdout, or None on any failure."""
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=10, cwd=Path(__file__).parent, check=False)
    except Exception:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _ram_gb() -> float | None:
    try:
        return round(psutil.virtual_memory().total / 1e9, 1)
    except Exception:
        return None


def _pkg_versions(names: tuple[str, ...]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for name in names:
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = None
    return out


@lru_cache(maxsize=8)
def provenance(packages: tuple[str, ...] = ()) -> Provenance:
    """Capture git, machine, and package-version provenance. Cached per package set -- git and machine
    don't change within a run, and the version lookup is the same for a given package tuple."""
    commit = _sh("git", "rev-parse", "--short", "HEAD")
    dirty = None if commit is None else bool(_sh("git", "status", "--porcelain"))
    return Provenance(
        git=GitInfo(commit=commit, dirty=dirty),
        machine=MachineInfo(
            host=platform.node(), cpu_count=os.cpu_count(), ram_gb=_ram_gb(), platform=platform.platform()
        ),
        versions=_pkg_versions(packages),
    )


def new_run_id() -> str:
    """A human-readable id shared by every record from one invocation (UTC, second precision)."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


class Results:
    """Append-only JSONL sink. One instance per invocation; `append` wraps each run/result pair in an
    `Envelope` and writes a single line. Creates the parent directory on construction."""

    def __init__(self, path: Path, *, bench: str, run_id: str, packages: tuple[str, ...] = ()) -> None:
        self.path = path
        self.bench = bench
        self.run_id = run_id
        self.packages = packages
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, run: BaseModel, result: BaseModel) -> None:
        prov = provenance(self.packages)
        env = Envelope(
            bench=self.bench,
            run_id=self.run_id,
            ts=datetime.now(UTC).isoformat(),
            git=prov.git,
            machine=prov.machine,
            versions=prov.versions,
            run=run.model_dump(mode="json"),
            result=result.model_dump(mode="json"),
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(env.model_dump_json() + "\n")
