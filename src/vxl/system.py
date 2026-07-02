"""Machine-local facts, config, and YAML I/O for the box this code runs on.

``System`` exposes what is true of *this* machine — CPU count, platform, hostname,
the RAM budget (:class:`System.Ram`), and the local storage roots (``store``/``scratch``).
Machine-specific knobs are sourced from ``VOXEL_*`` env vars, deliberately kept out of
the portable app config.

``load_yaml``/``save_yaml`` are the project's YAML helpers: pyyaml for loading,
ruyaml for comment-preserving writes.
"""

import io
import logging
import socket
import sys
from pathlib import Path
from typing import Any, ClassVar

import psutil
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from ruyaml import YAML

from vxlib import atomic_write

try:
    from yaml import CSafeLoader as _YamlLoader
except ImportError:
    from yaml import SafeLoader as _YamlLoader

log = logging.getLogger(__name__)


class System(BaseSettings):
    """This machine: ``VOXEL_*`` env-configured knobs plus introspected facts.

    Construct to read and validate the environment (each field maps to ``VOXEL_<FIELD>``).
    Exposes the local storage roots (``store``/``scratch`` as :class:`Path`, defaulting under
    ``dir``), the pure machine facts (``cpu_count``/``platform``/``hostname``), and the shared
    RAM budget (:class:`Ram`). Paths are resolved only; whoever writes creates the directories.
    """

    model_config = SettingsConfigDict(env_prefix="VOXEL_", extra="ignore")

    dir: Path = Field(default_factory=lambda: Path.home() / ".voxel")
    store: Path = Field(default_factory=lambda: Path.home() / ".voxel" / "store", description="VOXEL_STORE")
    scratch: Path = Field(default_factory=lambda: Path.home() / ".voxel" / "scratch", description="VOXEL_SCRATCH")
    max_ram_fraction: float = Field(default=0.75, gt=0.0, le=1.0)

    @model_validator(mode="before")
    @classmethod
    def _default_roots(cls, data: Any) -> Any:
        """Default store/scratch to ``<dir>/{store,scratch}`` when not set via VOXEL_STORE/VOXEL_SCRATCH."""
        if isinstance(data, dict):
            root = Path(data.get("dir") or Path.home() / ".voxel").expanduser()
            data.setdefault("store", root / "store")
            data.setdefault("scratch", root / "scratch")
        return data

    @field_validator("dir", "store", "scratch", mode="after")
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

    class Ram:
        """Weighted RAM-budget mediation for consumers sharing this machine's memory.

        Holds a policy fraction of available RAM and divides it among registered
        consumers in proportion to their weights. Consumers register via
        ``reserve()`` / ``release()`` and read their allocation via ``reserved()``.
        """

        _consumers: ClassVar[dict[str, float]] = {}

        @classmethod
        def total_bytes(cls) -> int:
            return psutil.virtual_memory().total

        @classmethod
        def available_bytes(cls) -> int:
            return psutil.virtual_memory().available

        @classmethod
        def max_bytes(cls) -> int:
            """Live policy cap: available system RAM * VOXEL_MAX_RAM_FRACTION."""
            return int(cls.available_bytes() * System().max_ram_fraction)

        @classmethod
        def reserve(cls, consumer_id: str, weight: float = 1.0) -> int:
            """Register ``consumer_id`` with ``weight``; return its share in bytes."""
            if weight <= 0:
                raise ValueError(f"weight must be > 0, got {weight}")
            cls._consumers[consumer_id] = weight
            return cls.reserved(consumer_id)

        @classmethod
        def release(cls, consumer_id: str) -> None:
            """Deregister ``consumer_id`` (no-op if not registered)."""
            cls._consumers.pop(consumer_id, None)

        @classmethod
        def reserved(cls, consumer_id: str) -> int:
            """Return the consumer's current weighted share in bytes.

            Raises KeyError if the consumer hasn't been registered via reserve().
            """
            if consumer_id not in cls._consumers:
                raise KeyError(consumer_id)
            total_weight = sum(cls._consumers.values()) or 1.0
            return int(cls.max_bytes() * cls._consumers[consumer_id] / total_weight)


def load_yaml[T: BaseModel](path: Path, model_cls: type[T]) -> T:
    """Load and validate a YAML file into ``model_cls`` (pyyaml, load-only)."""
    if not path.exists():
        raise FileNotFoundError(f"No {model_cls.__name__} found at {path}")
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=_YamlLoader)
    return model_cls.model_validate(data)


def save_yaml(path: Path, model: BaseModel) -> None:
    """Write ``model`` to ``path`` as YAML, preserving any comments already in the file (ruyaml)."""
    # text = yaml.safe_dump(model.model_dump(mode="json"), sort_keys=False, default_flow_style=False, width=4096)

    def _merge(dst: Any, src: Any) -> Any:
        """Overlay ``src`` (plain dict from a model dump) onto ``dst`` (a ruyaml CommentedMap),
        keeping ``dst``'s comments. Mappings merge key-by-key; everything else replaces."""
        if isinstance(dst, dict) and isinstance(src, dict):
            for key in [k for k in dst if k not in src]:
                del dst[key]  # field dropped from the model
            for key, value in src.items():
                cur = dst.get(key)
                dst[key] = _merge(cur, value) if isinstance(cur, dict) and isinstance(value, dict) else value
            return dst
        return src

    rt = YAML()  # round-trip mode: keeps comments, quotes, key order
    rt.preserve_quotes = True  # pyright: ignore[reportAttributeAccessIssue]
    rt.width = 4096  # pyright: ignore[reportAttributeAccessIssue]  # prevent unwanted line wrapping
    data: Any = model.model_dump(mode="json")
    if path.exists():
        data = _merge(rt.load(path.read_text(encoding="utf-8")), data)
    buf = io.StringIO()
    rt.dump(data, buf)
    text = buf.getvalue()

    atomic_write(path, text)
