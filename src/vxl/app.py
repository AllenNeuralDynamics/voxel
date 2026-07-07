"""Voxel application: instrument discovery and orchestration.

``VoxelApp`` discovers the instruments and templates under ``~/.voxel/`` and launches one at a
time. Selectable storage targets come from the machine's object-store registry (:attr:`System.remotes`).
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from vxl.instrument import Instrument, InstrumentConfig, InstrumentState
from vxl.system import Remote, System, load_yaml, save_yaml
from vxlib import Cell, Readable

logger = logging.getLogger(__name__)


TEMPLATES_DIR = Path(__file__).parent / "_templates"


class PresetLibrary:
    """A directory of saved :class:`InstrumentState` presets, one YAML file each."""

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.templates: dict[str, InstrumentState] = {}
        self.errors: dict[str, list[str]] = {}
        self.reload()

    def reload(self) -> None:
        """Rescan the directory for template states."""
        self.templates.clear()
        self.errors.clear()
        for p_file in self.directory.glob("*.yaml"):
            if p_file.name.endswith(".voxel.yaml"):
                continue  # InstrumentConfig templates, not InstrumentState presets
            try:
                self.templates[p_file.stem] = load_yaml(p_file, InstrumentState)
            except Exception as e:
                msg = f"Failed to load template '{p_file.name}': {e}"
                logger.warning(msg)
                self.errors.setdefault(p_file.stem, []).append(msg)

    def load(self, name: str) -> InstrumentState:
        """Return the named template. The instance is SHARED with the cache — do not mutate it in place;
        pass it to ``Bench.set``/``update`` (which builds a fresh validated graph)."""
        if name not in self.templates:
            raise FileNotFoundError(f"Template '{name}' not found.")
        return self.templates[name]

    def save(self, name: str, template: InstrumentState) -> None:
        """Persist `template` and refresh the cache."""
        save_yaml(self.directory / f"{name}.yaml", template)
        self.reload()


class InstrumentInfo(BaseModel):
    """Fault-tolerant read of an on-disk instrument: its ``config.yaml`` (parsed or per-field errors)
    plus the live ``bench.json`` if present. Used to list instruments without opening hardware."""

    config: InstrumentConfig | dict[str, str]
    bench: InstrumentState | dict[str, str] | None = None

    @property
    def ok(self) -> bool:
        return isinstance(self.config, InstrumentConfig) and not isinstance(self.bench, dict)

    @staticmethod
    def _load[T: BaseModel](path: Path, model: type[T]) -> T | dict[str, str]:
        """Parse ``path`` into ``model``, or return ``{loc: message}`` on failure.

        Field errors are keyed by their dotted location; model-level errors (empty ``loc``) by
        ``"<model>"``; file-level errors (the ``except Exception`` arm) by ``""``.
        """
        try:
            return load_yaml(path, model)
        except ValidationError as e:
            return {(".".join(str(p) for p in err["loc"]) or "<model>"): err["msg"] for err in e.errors()}
        except Exception as e:
            return {"": str(e)}

    @classmethod
    def read(cls, directory: Path | str) -> "InstrumentInfo":
        directory = Path(directory)
        bench = directory / "bench.json"
        return cls(
            config=cls._load(directory / "config.yaml", InstrumentConfig),
            bench=cls._load(bench, InstrumentState) if bench.exists() else None,
        )

    @classmethod
    def discover(cls, root: Path | str) -> dict[str, "InstrumentInfo"]:
        if not Path(root).is_dir():
            return {}
        return {d.stem: cls.read(d) for d in sorted(Path(root).iterdir()) if d.is_dir() and d.suffix == ".voxel"}


@dataclass(frozen=True)
class Discovered:
    """What the launcher can open: existing instruments (fault-tolerant) and shipped templates (valid)."""

    instruments: dict[str, InstrumentInfo]
    templates: dict[str, InstrumentConfig]


class VoxelApp:
    """Entry point: discover the instruments and templates on this box, and launch one.

    Instruments are ``<name>.voxel/`` directories under ``System().dir / "instruments"``.
    :meth:`discover` lists existing instruments + shipped templates (no hardware). :meth:`launch`
    opens an existing instrument; :meth:`launch_template` creates one from a template, then opens it.
    One instrument is active at a time — launching raises while another is open, so the caller
    ``close()``s then launches to switch.
    """

    def __init__(self) -> None:
        self._active: Cell[Instrument | None] = Cell(None)
        System().dir.mkdir(parents=True, exist_ok=True)  # ensure ~/.voxel/ and instruments/ exist
        self.instruments_dir.mkdir(exist_ok=True)

    @property
    def remotes(self) -> dict[str, Remote]:
        """The machine's configured object stores (name → connection + selectable roots), from
        :attr:`System.remotes` — the selectable acquisition targets. Local runs use no remote."""
        return System().remotes

    @property
    def active(self) -> Readable[Instrument | None]:
        """The launched instrument as a read-only reactive view (``.value`` / ``.subscribe``).

        Writes funnel through :meth:`launch` / :meth:`close` (which open/close hardware), so the
        value can't be swapped out from under the lifecycle.
        """
        return self._active

    @property
    def instruments_dir(self) -> Path:
        """Root holding the ``<name>.voxel`` instrument directories."""
        return System().dir / "instruments"

    def discover(self) -> Discovered:
        """Existing instruments (under ``instruments_dir``) + shipped templates. No hardware."""
        return Discovered(
            instruments=InstrumentInfo.discover(self.instruments_dir),
            templates=InstrumentConfig.discover(TEMPLATES_DIR),
        )

    async def launch(self, name: str) -> Instrument:
        """Open existing ``<name>.voxel`` and make it active. Raises if one is active or it's missing."""
        if (active := self._active.value) is not None:
            raise RuntimeError(f"'{active.path.stem}' is active; close it first")
        directory = self.instruments_dir / f"{name}.voxel"
        if not directory.is_dir():
            raise FileNotFoundError(f"No instrument '{name}' under {self.instruments_dir}")
        instrument = Instrument(directory)
        await instrument.open()
        await self._active.set(instrument)
        return instrument

    async def launch_template(self, template: str, name: str | None = None) -> Instrument:
        """Create an instrument from ``template`` (``name`` defaults to the template's), then launch it.

        Raises if one is already active, the template is unknown (``KeyError``), or an instrument of
        that name already exists (``FileExistsError``).
        """
        if (active := self._active.value) is not None:
            raise RuntimeError(f"'{active.path.stem}' is active; close it first")
        if (config := InstrumentConfig.discover(TEMPLATES_DIR).get(template)) is None:
            raise KeyError(f"No template '{template}'")
        target = name or template
        config.instantiate(target, self.instruments_dir)
        return await self.launch(target)

    async def close(self) -> None:
        """Close the active instrument (no-op if none)."""
        if (active := self._active.value) is not None:
            await active.close()
            await self._active.set(None)
