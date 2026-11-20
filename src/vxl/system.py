"""Machine-local facts and configuration for the box this code runs on.

``System`` exposes what is true of *this* machine — CPU count, platform, hostname,
the RAM budget, and the local storage roots (``store``/``scratch``). The Voxel processes on one machine
share its RAM budget through a registry file (:class:`MachineRegistry`).
Machine-specific knobs are sourced from ``VOXEL_*`` env vars and one machine file. A
control station's ``station.yaml`` is a superset of ``system.yaml`` and takes its place
when present; nodes and other non-control processes can use ``system.yaml`` or defaults.
"""

import logging
import os
import socket
import sqlite3
import sys
from collections.abc import Generator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path, PurePosixPath

import psutil
from cloudpathlib import S3Path
from dotenv import load_dotenv
from ome_zarr_writer import DirectS3, Local, StagedS3, Storage
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from vxlib.s3 import S3Store
from vxlib.schema import FrozenModel

from vxl._utils.files import load_yaml
from vxl.storage import ImageLocation, LocalLocation, LocationRole, LocationStatus, ObjectLocation, StorageSpec

log = logging.getLogger(__name__)


def voxel_home() -> Path:
    """Return the config and state home: ``$VOXEL_HOME`` when it is set, otherwise ``~/.voxel``.

    It holds the machine config and ``instruments/``. Move the data roots independently with ``VOXEL_STORE`` and
    ``VOXEL_SCRATCH``."""
    home = os.environ.get("VOXEL_HOME")
    return Path(home).expanduser() if home else Path.home() / ".voxel"


def yaml_source(settings_cls: type[BaseSettings], path: Path) -> InitSettingsSource:
    """Machine YAML as a settings source, read like every other Voxel YAML file; a missing file adds nothing."""
    return InitSettingsSource(settings_cls, (load_yaml(path) if path.is_file() else None) or {})


def load_voxel_env() -> None:
    """Load ``.env`` of the Voxel home into the process environment if present (a no-op when absent;
    existing vars win). A per-machine escape hatch for ambient settings the file layer can't
    reach: the ``VOXEL_*`` knobs *and* the AWS chain (``AWS_*``, ``S3_ENDPOINT_URL``) that
    s5cmd / boto3 / TensorStore read. ``VOXEL_HOME`` itself cannot be set there, because the file is found
    through it. Call once at startup, before constructing :class:`System` or any S3 client."""
    load_dotenv(voxel_home() / ".env", override=False)


class Remote(BaseModel):
    """A configured object store in the registry: the :class:`~vxlib.S3Store` ``connection`` plus the
    ``roots`` (display label -> write root) an operator may select. A root is a bucket, optionally
    narrowed by a key prefix (``bucket`` or ``bucket/prefix``). Holds no secrets -- credentials come
    from the AWS chain.

    The connection is held, not inherited: ``roots`` is operator-facing catalog data, while a
    :class:`~vxlib.S3Store` is a frozen *value* that writers hash to key their S3 client per
    connection. Subclassing would make a ``Remote`` an unhashable ``S3Store`` -- accepted by every
    ``store:`` field, then failing inside a cache lookup layers away. Pass ``.connection``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    connection: S3Store = S3Store()
    roots: dict[str, str] = Field(default_factory=dict, description="display label -> bucket or bucket/prefix")


def remote_store_fingerprint(store: S3Store) -> str:
    """Return a non-secret identity for matching one object store across machines.

    Roots and credential strategies are deliberately excluded: machines may expose different selectable roots and
    use different credentials while addressing the same S3-compatible service.
    """
    identity = f"{store.endpoint or ''}\0{store.region or ''}".encode()
    return f"s3:{sha256(identity).hexdigest()}"


_REGISTRY_VERSION = 1
_REGISTRY_SCHEMA = """
CREATE TABLE processes (
    pid INTEGER PRIMARY KEY,
    started REAL NOT NULL,
    name TEXT NOT NULL
) STRICT;
CREATE TABLE claims (
    pid INTEGER NOT NULL REFERENCES processes (pid) ON DELETE CASCADE,
    resource TEXT NOT NULL,
    consumer TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0),
    PRIMARY KEY (pid, resource, consumer)
) STRICT, WITHOUT ROWID;
"""

_PROCESS_START_TOLERANCE_S = (
    1.0  # psutil can report the start time of one process slightly differently in two processes
)


class ProcessEntry(FrozenModel):
    """A live Voxel process on this machine, with the amount each of its consumers claims of each resource."""

    pid: int
    name: str
    claims: dict[str, dict[str, float]]


class MachineRegistry:
    """The Voxel processes on this machine and their claims on shared resources.

    A claim is an amount of a named resource for one consumer of one process. What an amount means belongs to the
    class that manages that resource. A claim ends with its process.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._process = psutil.Process()

    @property
    def pid(self) -> int:
        """The process ID that this registry writes for."""
        return self._process.pid

    def join(self, name: str) -> None:
        """Register this process under ``name``, replacing an earlier registration."""
        row = (self.pid, self._process.create_time(), name)
        with self._transaction() as db:
            db.execute(
                "INSERT INTO processes VALUES (?, ?, ?) ON CONFLICT (pid) DO UPDATE SET name = excluded.name", row
            )

    def leave(self) -> None:
        """Remove this process and its claims."""
        with self._transaction() as db:
            db.execute("DELETE FROM processes WHERE pid = ?", (self.pid,))

    def processes(self) -> list[ProcessEntry]:
        """Return the live registered processes of this machine."""
        with self._transaction() as db:
            names = db.execute("SELECT pid, name FROM processes ORDER BY pid").fetchall()
            rows = db.execute("SELECT pid, resource, consumer, amount FROM claims").fetchall()
        claims: dict[int, dict[str, dict[str, float]]] = {pid: {} for pid, _ in names}
        for pid, resource, consumer, amount in rows:
            claims[pid].setdefault(resource, {})[consumer] = amount
        return [ProcessEntry(pid=pid, name=name, claims=claims[pid]) for pid, name in names]

    def claim(self, resource: str, consumer_id: str, amount: float) -> None:
        """Set the amount that a consumer of this process claims of ``resource``, registering the process if needed."""
        with self._transaction() as db:
            started, name = self._process.create_time(), self._process.name()
            db.execute("INSERT OR IGNORE INTO processes VALUES (?, ?, ?)", (self.pid, started, name))
            db.execute("INSERT OR REPLACE INTO claims VALUES (?, ?, ?, ?)", (self.pid, resource, consumer_id, amount))

    def unclaim(self, resource: str, consumer_id: str) -> None:
        """Remove a claim of this process; do nothing if there is none."""
        with self._transaction() as db:
            db.execute(
                "DELETE FROM claims WHERE pid = ? AND resource = ? AND consumer = ?", (self.pid, resource, consumer_id)
            )

    def claims(self, resource: str) -> dict[tuple[int, str], float]:
        """Return every live claim on ``resource``, by process ID and consumer."""
        with self._transaction() as db:
            rows = db.execute("SELECT pid, consumer, amount FROM claims WHERE resource = ?", (resource,)).fetchall()
        return {(pid, consumer): amount for pid, consumer, amount in rows}

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection]:
        """Open the registry with the write lock held and the rows of ended processes removed.

        A file of another version is emptied and rebuilt: live processes write their rows again on their next access.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self._path, timeout=10.0, isolation_level=None)
        try:
            db.execute("PRAGMA foreign_keys = ON")  # without it, the claims of a removed process would stay
            db.execute("BEGIN IMMEDIATE")
            if db.execute("PRAGMA user_version").fetchone()[0] != _REGISTRY_VERSION:
                db.execute("DROP TABLE IF EXISTS claims")
                db.execute("DROP TABLE IF EXISTS processes")
                for statement in _REGISTRY_SCHEMA.split(";"):
                    db.execute(statement)
                db.execute(f"PRAGMA user_version = {_REGISTRY_VERSION}")
            for pid, started in db.execute("SELECT pid, started FROM processes").fetchall():
                try:  # a reused pid has another start time, and a pid of another user's process is not ours
                    alive = abs(psutil.Process(pid).create_time() - started) < _PROCESS_START_TOLERANCE_S
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    alive = False
                if not alive:
                    db.execute("DELETE FROM processes WHERE pid = ?", (pid,))
            yield db
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()


class RamBudget:
    """Divide a machine's RAM budget among the consumers of every registered process, in proportion to their
    weights. It keeps the weights of its own consumers and writes them again on each read, so a registry that was
    emptied or replaced is restored."""

    _RESOURCE = "ram"

    def __init__(self, machine: "System") -> None:
        self._machine = machine
        self._weights: dict[str, float] = {}

    def reserve(self, consumer_id: str, weight: float = 1.0) -> int:
        """Register a consumer of this process and return its share in bytes."""
        if weight <= 0:
            raise ValueError(f"weight must be > 0, got {weight}")
        self._weights[consumer_id] = weight
        return self.reserved(consumer_id)

    def release(self, consumer_id: str) -> None:
        """Remove a consumer of this process; do nothing if it is not registered."""
        self._weights.pop(consumer_id, None)
        self._machine.registry.unclaim(self._RESOURCE, consumer_id)

    def reserved(self, consumer_id: str) -> int:
        """Return the current share of a consumer of this process, in bytes.

        Raises KeyError if the consumer is not registered.
        """
        own = self._weights[consumer_id]
        registry = self._machine.registry
        for consumer, weight in self._weights.items():
            registry.claim(self._RESOURCE, consumer, weight)
        return int(self._machine.ram_budget_bytes * own / sum(registry.claims(self._RESOURCE).values()))


class System(BaseSettings):
    """This machine: ``VOXEL_*`` env knobs, machine YAML config, and introspected facts.

    Construct to read and validate the environment plus ``~/.voxel/station.yaml`` when it exists,
    otherwise ``~/.voxel/system.yaml`` (init > env > yaml). The selected file is not merged with
    the fallback. Exposes the local storage roots (``store``/``scratch``, overridable via
    ``VOXEL_STORE``/``VOXEL_SCRATCH``), the object-store registry (:attr:`remotes`), the fixed config
    home (:attr:`dir`), the pure machine
    facts (``cpu_count``/``platform``/``hostname``), and the RAM budget that the Voxel processes of this
    machine share (:attr:`ram`). Paths
    are resolved only; whoever writes creates them.
    """

    model_config = SettingsConfigDict(env_prefix="VOXEL_", extra="ignore")

    store: Path = Field(default_factory=lambda: voxel_home() / "store", description="VOXEL_STORE")
    scratch: Path = Field(default_factory=lambda: voxel_home() / "scratch", description="VOXEL_SCRATCH")
    max_ram_fraction: float = Field(
        default=0.75,
        gt=0.0,
        le=1.0,
        description=(
            "VOXEL_MAX_RAM_FRACTION — fraction of *available* (not total) RAM that registered consumers "
            "divide between them by weight. Because the denominator excludes the OS and other processes, "
            "this is a share of what is free at the moment it is read, not a fixed provision."
        ),
    )
    remotes: dict[str, Remote] = Field(
        default_factory=dict, description="object-store name -> connection (from the selected machine config)"
    )

    @classmethod
    def config_path(cls) -> Path:
        """Return the selected machine config: station first, then system.

        Selection is whole-file precedence, not a merge. This keeps exactly one authority for
        structured machine settings while allowing nodes to run without a station identity.
        """
        station = voxel_home() / "station.yaml"
        return station if station.is_file() else voxel_home() / "system.yaml"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Layer the selected machine YAML under env (priority: init > env > yaml)."""
        del dotenv_settings, file_secret_settings
        return (init_settings, env_settings, yaml_source(settings_cls, cls.config_path()))

    @property
    def dir(self) -> Path:
        """The fixed config/state home (``~/.voxel``); see :func:`voxel_home`."""
        return voxel_home()

    @field_validator("store", "scratch", mode="after")
    @classmethod
    def _expand(cls, p: Path) -> Path:
        return p.expanduser()

    @staticmethod
    def cpu_count() -> int:
        return psutil.cpu_count(logical=True) or 1

    @staticmethod
    def platform() -> str:
        return sys.platform

    @staticmethod
    def hostname() -> str:
        return socket.gethostname()

    @staticmethod
    def total_ram_bytes() -> int:
        return psutil.virtual_memory().total

    @staticmethod
    def available_ram_bytes() -> int:
        return psutil.virtual_memory().available

    @property
    def ram_budget_bytes(self) -> int:
        """Available RAM times ``max_ram_fraction``, read now."""
        return int(self.available_ram_bytes() * self.max_ram_fraction)

    @property
    def registry(self) -> "MachineRegistry":
        """The registry of the Voxel processes on this machine. Its file is named after the machine, so two
        machines that share a home by mistake do not share a registry."""
        return MachineRegistry(self.dir / "run" / f"machine-{self.hostname()}.db")

    @property
    def ram(self) -> "RamBudget":
        """A new budget of this machine's RAM. Keep it for as long as its consumers live."""
        return RamBudget(self)

    @staticmethod
    def local_ip() -> str:
        """Return the best-effort outbound IPv4 address, falling back to loopback."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
                connection.settimeout(0.1)
                connection.connect(("8.8.8.8", 80))
                return connection.getsockname()[0]
        except OSError:
            return "127.0.0.1"

    def resolve_storage(self, spec: StorageSpec, subpath: PurePosixPath | None = None) -> Storage:
        """Resolve portable storage against this machine's configuration."""
        relpath = spec.path / (subpath or PurePosixPath())
        if spec.remote is None:
            return Local(target=self.store / relpath)

        if spec.remote.store not in self.remotes:
            raise KeyError(f"unknown remote store '{spec.remote.store}'; configured: {sorted(self.remotes)}")
        store = self.remotes[spec.remote.store].connection
        target = S3Path(f"s3://{spec.remote.root}") / relpath.as_posix()
        if spec.remote.stage:
            return StagedS3(scratch=self.scratch / relpath, target=target, store=store)
        return DirectS3(target=target, store=store)

    def describe_image_location(self, spec: StorageSpec, target: Path | S3Path) -> ImageLocation:
        """The location of an image that a writer writes at ``target``, for the acquisition record."""
        if spec.remote is None:
            if not isinstance(target, Path):
                raise TypeError(f"local storage resolved to a non-local target: {target}")
            return LocalLocation(
                role=LocationRole.DESTINATION,
                status=LocationStatus.WRITING,
                host=self.hostname(),
                path=str(target),
            )

        if not isinstance(target, S3Path):
            raise TypeError(f"object storage resolved to a non-object target: {target}")
        return ObjectLocation(
            role=LocationRole.DESTINATION,
            status=LocationStatus.WRITING,
            host=self.hostname(),
            store=spec.remote.store,
            bucket=target.bucket,
            key=target.key,
        )


__all__ = [
    "MachineRegistry",
    "ProcessEntry",
    "RamBudget",
    "Remote",
    "System",
    "load_voxel_env",
    "remote_store_fingerprint",
    "voxel_home",
    "yaml_source",
]
