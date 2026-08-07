"""Voxel application: instrument discovery and orchestration.

``VoxelApp`` discovers the instruments and templates under ``~/.voxel/`` and launches one at a
time. Selectable storage targets come from the machine's object-store registry (:attr:`System.remotes`).
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import AnyWebsocketUrl
from vxl_catalog import Catalog, FileCatalogBackend

from vxl.camera import resolve_storage
from vxl.errors import Loaded
from vxl.instrument import Instrument, InstrumentBench, InstrumentConfig, InstrumentInspection, InstrumentState
from vxl.instrument.publishers import PreviewPub, StatusPub
from vxl.system import Remote, System
from vxlib import Cell, Readable, load_yaml, save_yaml

logger = logging.getLogger(__name__)


TEMPLATES_DIR = Path(__file__).parent / "_templates"


def _discover_templates(root: Path) -> dict[str, InstrumentConfig]:
    """Return valid templates while reporting every structured failure."""
    found: dict[str, InstrumentConfig] = {}
    if not root.is_dir():
        return found
    for path in sorted(root.glob("*.voxel.yaml")):
        name = path.name.removesuffix(".voxel.yaml")
        checked = InstrumentBench.check_config(path)
        if checked.ok and isinstance(checked.config, Loaded):
            found[name] = checked.config.value
            continue
        logger.warning(
            "Skipping config '%s.voxel.yaml': %s",
            name,
            "; ".join(violation.msg for violation in checked.violations),
        )
    return found


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
        pass it to ``InstrumentBench.set``/``update`` (which builds a fresh validated graph)."""
        if name not in self.templates:
            raise FileNotFoundError(f"Template '{name}' not found.")
        return self.templates[name]

    def save(self, name: str, template: InstrumentState) -> None:
        """Persist `template` and refresh the cache."""
        save_yaml(self.directory / f"{name}.yaml", template)
        self.reload()


@dataclass(frozen=True)
class Discovered:
    """What the launcher can open: existing instruments (fault-tolerant) and shipped templates (valid)."""

    instruments: dict[str, InstrumentInspection]
    templates: dict[str, InstrumentConfig]


class VoxelApp:
    """Entry point: discover the instruments and templates on this box, and launch one.

    Instruments are ``<name>.voxel/`` directories under ``System().dir / "instruments"``.
    :meth:`discover` lists existing instruments + shipped templates (no hardware). :meth:`launch`
    opens an existing instrument; :meth:`launch_template` creates one from a template, then opens it.
    One instrument is active at a time — launching raises while another is open, so the caller
    ``close()``s then launches to switch.
    """

    def __init__(self, catalog: Catalog | None = None) -> None:
        self._active: Cell[Instrument | None] = Cell(None)
        self._system = System()
        self._system.dir.mkdir(parents=True, exist_ok=True)  # ensure ~/.voxel/ and instruments/ exist
        self.instruments_dir.mkdir(exist_ok=True)
        self._catalog = catalog or Catalog(
            FileCatalogBackend(self._system.dir / "catalog"),
            resolve_root=lambda spec: resolve_storage(spec).target,
        )
        self._status_pub: StatusPub | None = None
        self._preview_pub: PreviewPub | None = None

    @property
    def catalog(self) -> Catalog:
        """The acquisition catalog shared with the active instrument."""
        return self._catalog

    @property
    def remotes(self) -> dict[str, Remote]:
        """The machine's configured object stores (name → connection + selectable roots), from
        :attr:`System.remotes` — the selectable acquisition targets. Local runs use no remote."""
        return self._system.remotes

    @property
    def preview_url(self) -> AnyWebsocketUrl | None:
        """External preview WebSocket URL, or ``None`` when the web host supplies it."""
        return self._system.preview_url

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
        return self._system.dir / "instruments"

    def discover(self) -> Discovered:
        """Existing instruments (under ``instruments_dir``) + shipped templates. No hardware."""
        instruments = (
            {
                directory.stem: InstrumentBench.check(directory)
                for directory in sorted(self.instruments_dir.glob("*.voxel"))
                if directory.is_dir()
            }
            if self.instruments_dir.is_dir()
            else {}
        )
        return Discovered(
            instruments=instruments,
            templates=_discover_templates(TEMPLATES_DIR),
        )

    async def launch(self, name: str) -> Instrument:
        """Open existing ``<name>.voxel`` and make it active. Raises if one is active or it's missing."""
        if (active := self._active.value) is not None:
            raise RuntimeError(f"'{active.path.stem}' is active; close it first")
        directory = self.instruments_dir / f"{name}.voxel"
        if not directory.is_dir():
            raise FileNotFoundError(f"No instrument '{name}' under {self.instruments_dir}")
        instrument = Instrument.from_path(directory, catalog=self._catalog)
        await instrument.open()
        try:
            await self._open_publishers(instrument)
        except BaseException:
            try:
                await self._close_publishers()
                await instrument.close()
            except Exception:
                logger.exception("Failed to clean up preview publishers after launch error")
            raise
        await self._active.set(instrument)
        return instrument

    async def launch_template(self, template: str, name: str | None = None) -> Instrument:
        """Create an instrument from ``template`` (``name`` defaults to the template's), then launch it.

        Raises if one is already active, the template is unknown (``KeyError``), or an instrument of
        that name already exists (``FileExistsError``).
        """
        if (active := self._active.value) is not None:
            raise RuntimeError(f"'{active.path.stem}' is active; close it first")
        if (config := _discover_templates(TEMPLATES_DIR).get(template)) is None:
            raise KeyError(f"No template '{template}'")
        target = name or template
        config.instantiate(target, self.instruments_dir)
        return await self.launch(target)

    def archive_bench(self, name: str) -> Path:
        """Archive ``bench.json`` under the next available backup name.

        The next launch uses ``config.default`` because no live bench remains. Raises if the instrument is
        active, missing, or has no ``bench.json``.
        """
        if (active := self._active.value) is not None and active.path.stem == name:
            raise RuntimeError(f"'{name}' is active; close it first")
        directory = self.instruments_dir / f"{name}.voxel"
        if not directory.is_dir():
            raise FileNotFoundError(f"No instrument '{name}' under {self.instruments_dir}")
        bench = directory / "bench.json"
        if not bench.exists():
            raise FileNotFoundError(f"No bench.json to archive for '{name}'")

        archive = directory / "bench.bak.json"
        index = 2
        while archive.exists():
            archive = directory / f"bench.bak.{index}.json"
            index += 1
        bench.rename(archive)
        return archive

    async def close(self) -> None:
        """Close the active instrument (no-op if none)."""
        if (active := self._active.value) is not None:
            await self._close_publishers()
            await active.close()
            await self._active.set(None)

    async def _open_publishers(self, instrument: Instrument) -> None:
        """Open configured network publishers for one active instrument."""
        feed_endpoint = self._system.instrument_feed_endpoint
        frame_endpoint = self._system.preview_frame_endpoint
        if feed_endpoint is None and frame_endpoint is None:
            return

        source_id = f"{self._system.hostname()}/{instrument.path.stem}"
        if feed_endpoint is not None:
            self._status_pub = StatusPub(feed_endpoint, source_id)
            await self._status_pub.open(instrument.feed)
        if frame_endpoint is not None:
            self._preview_pub = PreviewPub(frame_endpoint, source_id)
            await self._preview_pub.open(instrument.feed)

    async def _close_publishers(self) -> None:
        """Release configured publisher sockets."""
        publishers = (self._preview_pub, self._status_pub)
        self._preview_pub = None
        self._status_pub = None
        for publisher in publishers:
            if publisher is None:
                continue
            try:
                await publisher.close()
            except Exception:
                logger.exception("Failed to close %s", type(publisher).__name__)
