"""Interactive checkup TUI for a Tiger box.

Drives everything through `TigerHub` so what gets exercised is the public driver API — reservation,
the pollers, and the whole ops/protocol stack beneath them.

Operations are grouped into tiers by how much they can disturb the instrument:

    read       queries only. Always safe, and where nearly every parsing bug has been found.
    params     writes a parameter back to the value it already had, then re-reads it. Round-trips
               the write path without changing the machine's configuration.
    joystick   disables and re-enables joystick input, restoring the original mapping.
    motion     a small relative move and back. Needs an explicit axis and delta.
    stepshoot  configures the ring buffer, queues one move, then resets. Nothing moves without TTL.

`home`, `zero` and the scan starts are deliberately absent: homing can drive an objective into a
sample, zeroing silently destroys calibration, and a scan start begins continuous motion. Those want
a person deciding, not a menu entry.

Usage:
    python -m vxl_drivers.tigerhub.tui --port COM3
    python -m vxl_drivers.tigerhub.tui --port COM3 --check          # run the read tier and exit
    python -m vxl_drivers.tigerhub.tui --port COM3 --check --debug   # ... with raw frame logging
"""

import argparse
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from vxl_drivers.tigerhub.hub import TigerHub
from vxl_drivers.tigerhub.model.box_info import BoxInfo
from vxl_drivers.tigerhub.ops.params import TigerParam, TigerParams
from vxl_drivers.tigerhub.ops.step_shoot import RingBufferMode, StepShootConfig, TTLIn0Mode, TTLOut0Mode

# Parameters shown in the axis table, in display order. Each is read for *all* axes in one command,
# which is both far quicker than per-axis reads and the shape that exposed the reply-layout bugs.
TABLE_PARAMS: tuple[tuple[str, TigerParam[Any]], ...] = (
    ("speed", TigerParams.SPEED),
    ("accel", TigerParams.ACCEL),
    ("bklash", TigerParams.BACKLASH),
    ("home", TigerParams.HOME_POS),
    ("lim lo", TigerParams.LIMIT_LOW),
    ("lim hi", TigerParams.LIMIT_HIGH),
    ("cnts", TigerParams.ENCODER_CNTS),
    ("ctrl", TigerParams.CONTROL_MODE),
    ("Kp", TigerParams.PID_P),
    ("Ki", TigerParams.PID_I),
    ("Kd", TigerParams.PID_D),
    ("hspd", TigerParams.HOME_SPEED),
)

TIERS = ("read", "params", "joystick", "motion", "stepshoot")


# ------------------------------------------------------------------------------- checkup machinery


@dataclass
class Result:
    """One operation's outcome. `detail` is a short human summary, not the raw value."""

    name: str
    tier: str
    ok: bool
    detail: str


@dataclass
class Checkup:
    hub: TigerHub
    results: list[Result] = field(default_factory=list)

    def step(self, name: str, tier: str, fn: Callable[[], Any]) -> Any:
        """Run one operation, record whether it worked, and return its value (None on failure).

        Failures are recorded rather than raised so a single unsupported command doesn't end the
        run — the point is to find out which operations work, not to stop at the first that doesn't.
        """
        try:
            value = fn()
        except Exception as exc:
            self.results.append(Result(name, tier, ok=False, detail=f"{type(exc).__name__}: {exc}"))
            return None
        self.results.append(Result(name, tier, ok=True, detail=_summarise(value)))
        return value

    # -- read ------------------------------------------------------------------------------------

    def run_read(self) -> None:
        box_ = self.hub.box
        info: BoxInfo | None = self.step("info(refresh=True)", "read", lambda: box_.info(refresh=True))
        self.step("current_mode", "read", box_.current_mode)
        self.step("is_busy", "read", box_.is_busy)
        self.step("available_axes", "read", self.hub.available_axes)
        self.step("available_axes(all)", "read", lambda: self.hub.available_axes(commandable_only=False))

        axes = sorted(info.axes) if info else []
        if not axes:
            return

        self.step("get_position(all)", "read", lambda: box_.get_position(axes))
        self.step("is_axis_moving(all)", "read", lambda: box_.is_axis_moving(axes))
        for label, param in TABLE_PARAMS:
            self.step(f"get_param {param.verb} ({label})", "read", lambda p=param: box_.get_param(p, axes))
        for axis in axes:
            self.step(f"get_axis_state {axis}", "read", lambda a=axis: box_.get_axis_state(a))
        self.step("get_joystick_mapping", "read", lambda: box_.get_joystick_mapping(refresh=True))

        if info:
            for card in info.cards:
                self.step(f"get_ttl_config 0x{card.addr:X}", "read", lambda a=card.addr: box_.get_ttl_config(a))
                self.step(f"ttl_out_state 0x{card.addr:X}", "read", lambda a=card.addr: box_.ttl_out_state(a))

        # Reservation and the pollers: reserve, let a fast tick land, then read the cache back.
        reserved: list[str] = []
        for a in self.hub.available_axes():
            if self.step(f"reserve_axis {a}", "read", lambda x=a: self.hub.reserve_axis(x)):
                reserved.append(a)
        if reserved:
            time.sleep(0.5)
            self.step(
                "poller cache populated",
                "read",
                lambda: _require(
                    {a: self.hub.get_axis_state_cached(a) for a in reserved},
                    lambda got: all("position_steps" in v for v in got.values()),
                    "some axes have no cached position",
                ),
            )
            for a in reserved:
                self.step(f"release_axis {a}", "read", lambda x=a: self.hub.release_axis(x))

    # -- params ----------------------------------------------------------------------------------

    def run_params(self, axis: str) -> None:
        """Write a parameter back to the value it already holds, then confirm the read agrees."""
        box_ = self.hub.box
        for param in (TigerParams.SPEED, TigerParams.BACKLASH, TigerParams.ACCEL):

            def round_trip(p: TigerParam[Any] = param) -> Any:
                before = box_.get_param(p, [axis])
                if axis not in before:
                    msg = f"{p.verb} not readable on {axis}; nothing to write back"
                    raise RuntimeError(msg)
                box_.set_param(p, {axis: before[axis]})
                after = box_.get_param(p, [axis])
                if after.get(axis) != before[axis]:
                    msg = f"{p.verb} read back as {after.get(axis)!r}, wrote {before[axis]!r}"
                    raise RuntimeError(msg)
                return after[axis]

            self.step(f"set_param {param.verb} round-trip on {axis}", "params", round_trip)

    # -- joystick --------------------------------------------------------------------------------

    def run_joystick(self) -> None:
        box_ = self.hub.box
        before = self.step("get_joystick_mapping", "joystick", lambda: box_.get_joystick_mapping(refresh=True))
        if before is None:
            return
        self.step("disable_joystick_inputs", "joystick", box_.disable_joystick_inputs)
        self.step("enable_joystick_inputs", "joystick", box_.enable_joystick_inputs)
        self.step(
            "joystick mapping restored",
            "joystick",
            lambda: _require(
                box_.get_joystick_mapping(refresh=True),
                lambda after: after == before,
                "mapping was not restored to its original value",
            ),
        )

    # -- motion ----------------------------------------------------------------------------------

    def run_motion(self, axis: str, delta: float) -> None:
        """Move `delta` controller units and come back, checking the position each way."""
        box_ = self.hub.box
        start = self.step(f"get_position {axis} (start)", "motion", lambda: box_.get_position([axis]))
        if not start:
            return
        origin = start[axis]

        def out_and_back() -> str:
            box_.move_rel({axis: delta}, wait=True)
            moved = box_.get_position([axis])[axis]
            if abs(moved - (origin + delta)) > max(2.0, abs(delta) * 0.02):
                msg = f"expected ~{origin + delta}, got {moved}"
                raise RuntimeError(msg)
            box_.move_rel({axis: -delta}, wait=True)
            back = box_.get_position([axis])[axis]
            if abs(back - origin) > 2.0:
                msg = f"did not return: started {origin}, ended {back}"
                raise RuntimeError(msg)
            return f"{origin} -> {moved} -> {back}"

        self.step(f"move_rel {axis} +/-{delta} (wait)", "motion", out_and_back)

    # -- stepshoot -------------------------------------------------------------------------------

    def run_stepshoot(self, axis: str, delta: float) -> None:
        """Configure the ring buffer and queue one move. Nothing moves without a TTL pulse."""
        box_ = self.hub.box
        cfg = StepShootConfig(
            axes=[axis],
            in0_mode=TTLIn0Mode.MOVE_TO_NEXT_REL_POSITION,
            out0_mode=TTLOut0Mode.PULSE_AFTER_MOVING,
            ring_mode=RingBufferMode.TTL_TRIGGERED,
        )
        configured = self.step(
            f"configure_step_shoot {axis}",
            "stepshoot",
            lambda: box_.configure_step_shoot(cfg) or True,
        )
        try:
            if configured:
                self.step("queue_step_shoot_rel", "stepshoot", lambda: box_.queue_step_shoot_rel({axis: delta}) or True)
        finally:
            # Always reset: leaving the card in TTL_TRIGGERED with a queued move means the next
            # stray pulse moves the stage.
            self.step("reset_step_shoot", "stepshoot", lambda: box_.reset_step_shoot() or True)


def _require(value: Any, predicate: Callable[[Any], bool], message: str) -> Any:
    """Return `value`, or raise if it fails `predicate`. Lets a check assert from inside `step`."""
    if not predicate(value):
        raise RuntimeError(message)
    return value


def _summarise(value: Any) -> str:
    """One-line summary of a returned value, short enough for a table cell."""
    if value is None:
        return "—"
    if isinstance(value, Mapping):
        items = list(value.items())[:4]
        body = ", ".join(f"{k}={_fmt(v)}" for k, v in items)
        return f"{body}{', …' if len(value) > 4 else ''}" if items else "{}"
    if isinstance(value, str):
        return value if len(value) <= 60 else value[:57] + "…"
    if isinstance(value, Sequence):
        return f"{len(value)} item(s): {', '.join(str(v) for v in value[:6])}" if value else "empty"
    text = str(value).replace("\n", " ")
    return text if len(text) <= 60 else text[:57] + "…"


def _fmt(v: Any) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


# --------------------------------------------------------------------------------------- rendering


def header_panel(port: str, info: BoxInfo | None, mode: Any) -> Panel:
    g = Table.grid(padding=(0, 2))
    g.add_column(style="bold")
    g.add_column(style="cyan")
    g.add_row("Port", port)
    g.add_row("Version", (info.version if info else None) or "—")
    g.add_row("Mode", str(mode) if mode else "—")
    g.add_row("Cards", str(len(info.cards)) if info else "—")
    g.add_row("Axes", ", ".join(sorted(info.axes)) if info else "—")
    return Panel(g, title="[bold]Tiger checkup[/bold]", border_style="yellow", expand=False)


def axes_table(hub: TigerHub, info: BoxInfo) -> Table:
    """Axes as rows, properties as columns, every parameter fetched in one command per parameter."""
    axes = sorted(info.axes)
    box_ = hub.box
    pos = _safe(lambda: box_.get_position(axes), {})
    busy = _safe(lambda: box_.is_axis_moving(axes), {})
    jmap = _safe(box_.get_joystick_mapping, {})
    values = {label: _safe(lambda p=param: box_.get_param(p, axes), {}) for label, param in TABLE_PARAMS}

    t = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False)
    t.add_column("Ax", style="bold")
    t.add_column("type")
    t.add_column("card")
    t.add_column("pos", justify="right", style="cyan")
    t.add_column("", justify="center")  # busy dot
    for label, _ in TABLE_PARAMS:
        t.add_column(label, justify="right")
    t.add_column("joy")

    for a in axes:
        ax = info.axes[a]
        cells = [
            a,
            ax.device_type.name.lower() + ("" if ax.device_type.commandable else " !"),
            f"0x{ax.card_hex:X}" if ax.card_hex is not None else "—",
            _fmt(pos[a]) if a in pos else "—",
            Text("●", style="green") if busy.get(a) else Text("·", style="dim"),
        ]
        cells += [_fmt(values[label][a]) if a in values[label] else "—" for label, _ in TABLE_PARAMS]
        cells.append(str(jmap.get(a, "—")))
        t.add_row(*cells)
    return t


def cards_table(info: BoxInfo) -> Table:
    t = Table(box=box.SIMPLE, expand=True, pad_edge=False)
    for name in ("Card", "Board", "Axes", "FW", "Date", "Modules"):
        t.add_column(name, style="green" if name == "Modules" else None)
    for c in info.cards:
        t.add_row(
            f"0x{c.addr:X}",
            str(c.board),
            ", ".join(c.axes) or "—",
            str(c.fw),
            str(c.date),
            ", ".join(sorted(c.mods)) or "—",
        )
    return t


def axis_panel(hub: TigerHub, info: BoxInfo, axis: str) -> Panel:
    """Everything about one axis, including the INFO dump's own unit."""
    ax = info.axes[axis]
    state = _safe(lambda: hub.box.get_axis_state(axis), None)
    g = Table.grid(padding=(0, 2))
    g.add_column(style="bold")
    g.add_column(style="cyan", justify="right")
    g.add_row("type", f"{ax.device_type.name} ({ax.device_type.value})")
    g.add_row("commandable", str(ax.device_type.commandable))
    g.add_row("card / slot", f"0x{ax.card_hex:X} / {ax.card_index}" if ax.card_hex is not None else "—")
    g.add_row("axis id", str(ax.axis_id))
    g.add_row("enc cnts", str(ax.enc_cnts_per_mm))
    if state is not None:
        g.add_row("unit", state.unit or "—")
        g.add_row("position", f"{state.pos_current_mm} {state.unit or ''}")
        g.add_row("limits", f"{state.limit_min} … {state.limit_max} {state.unit or ''}")
        g.add_row("run speed", str(state.run_speed_mm_s))
        g.add_row("profile", str(state.axis_profile))
        g.add_row("input dev", str(state.input_device))
        g.add_row("cmd / move", f"{state.cmd_stat} / {state.move_stat}")
        g.add_row("motor / loop", f"{state.motor_enable} / {state.axis_enable}")
    return Panel(g, title=f"[bold]Axis {axis}[/bold]", border_style="cyan", expand=False)


def results_table(results: Sequence[Result]) -> Table:
    t = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False)
    t.add_column("", justify="center", width=3)
    t.add_column("tier", style="dim")
    t.add_column("operation", style="bold")
    t.add_column("result")
    for r in results:
        t.add_row(
            Text("ok" if r.ok else "FAIL", style="green" if r.ok else "red"),
            r.tier,
            r.name,
            Text(r.detail, style="" if r.ok else "red"),
        )
    return t


def _safe(fn: Callable[[], Any], fallback: Any) -> Any:
    """Call `fn`, returning `fallback` on any failure — display code must not crash the TUI."""
    try:
        return fn()
    except Exception:
        return fallback


HELP = """[bold]Views[/bold]
  table                 all axes x all parameters (one command per parameter)
  axes                  detected axes with type and card
  show X [Y ...]        per-axis detail, including the unit INFO reports
  cards                 cards, boards and firmware modules
  poll                  the hub's cached state for reserved axes

[bold]Checks[/bold]  [dim](results are tabulated; a failure never stops the run)[/dim]
  check                 read tier only — queries, always safe
  check params [AXIS]   + write each parameter back to its current value and re-read
  check joystick        + disable / enable / restore joystick input
  check motion AXIS D   + move AXIS by D controller units and back
  check stepshoot AX D  + configure ring buffer, queue one move, reset

[bold]Session[/bold]
  debug on|off          raw frame logging (shows retries, i.e. the live corruption rate)
  refresh               re-read BoxInfo
  help / quit"""


# ------------------------------------------------------------------------------------- main loop


def _resolve_axis(console: Console, info: BoxInfo, name: str | None) -> str | None:
    if not name:
        console.print("[red]This command needs an axis.[/red]")
        return None
    axis = name.upper()
    if axis not in info.axes:
        console.print(f"[red]Unknown axis {axis!r}.[/red] Known: {', '.join(sorted(info.axes))}")
        return None
    return axis


def _run_checks(console: Console, hub: TigerHub, tier: str, args: list[str], info: BoxInfo) -> None:
    checkup = Checkup(hub)
    checkup.run_read()
    if tier == "params":
        axis = _resolve_axis(console, info, args[0] if args else next(iter(sorted(info.axes)), None))
        if axis:
            checkup.run_params(axis)
    elif tier == "joystick":
        checkup.run_joystick()
    elif tier in ("motion", "stepshoot"):
        axis = _resolve_axis(console, info, args[0] if args else None)
        if axis is None:
            return
        try:
            delta = float(args[1]) if len(args) > 1 else 100.0
        except ValueError:
            console.print(f"[red]Bad delta {args[1]!r}.[/red]")
            return
        console.print(f"[yellow]{tier} tier on {axis} with delta {delta:g} controller units.[/yellow]")
        if tier == "motion":
            checkup.run_motion(axis, delta)
        else:
            checkup.run_stepshoot(axis, delta)

    failed = [r for r in checkup.results if not r.ok]
    console.print(results_table(checkup.results))
    style = "red" if failed else "green"
    console.print(
        Panel(
            f"{len(checkup.results) - len(failed)} ok, {len(failed)} failed",
            border_style=style,
            expand=False,
        ),
    )


def _set_debug(console: Console, on: bool) -> None:
    logging.getLogger("tiger_protocol").setLevel(logging.DEBUG if on else logging.WARNING)
    if on and not logging.getLogger().handlers:
        logging.basicConfig(level=logging.DEBUG)
    console.print(f"[cyan]Frame logging {'on' if on else 'off'}.[/cyan]")


def _poll_table(hub: TigerHub, info: BoxInfo) -> Table | str:
    """The hub's cached state for whatever is currently reserved."""
    rows = [(a, hub.get_axis_state_cached(a)) for a in sorted(info.axes)]
    rows = [(a, v) for a, v in rows if v]
    if not rows:
        return "No axes are reserved, so the pollers have nothing to read."
    keys = sorted({k for _, v in rows for k in v})
    t = Table(box=box.SIMPLE_HEAD, expand=False, pad_edge=False)
    t.add_column("Ax", style="bold")
    for k in keys:
        t.add_column(k, justify="right")
    for axis, cached in rows:
        t.add_row(axis, *[_fmt(cached[k]) if k in cached else "—" for k in keys])
    return t


def _handle(console: Console, hub: TigerHub, info: BoxInfo, port: str, cmd: str, rest: list[str]) -> BoxInfo:
    """Run one command, returning the BoxInfo to use from here on (refresh replaces it)."""
    if cmd == "help":
        console.print(Panel(HELP, border_style="grey50", expand=False))
    elif cmd == "refresh":
        info = hub.box.info(refresh=True)
        console.print(header_panel(port, info, hub.box.current_mode()))
    elif cmd == "table":
        console.print(axes_table(hub, info))
    elif cmd == "axes":
        listing = ", ".join(f"{a}[dim]:{info.axes[a].device_type.name.lower()}[/dim]" for a in sorted(info.axes))
        console.print(Panel(listing, title="Detected axes", border_style="cyan", expand=False))
    elif cmd == "cards":
        console.print(cards_table(info))
    elif cmd == "poll":
        console.print(Panel(_poll_table(hub, info), title="Hub cache", border_style="cyan", expand=False))
    elif cmd == "show":
        targets = [t.upper() for t in rest] or sorted(info.axes)
        panels = [axis_panel(hub, info, a) for a in targets if a in info.axes]
        if panels:
            console.print(Columns(panels, padding=(0, 1)))
        else:
            console.print("[red]No known axes in that list.[/red]")
    elif cmd == "check":
        tier = rest[0].lower() if rest else "read"
        if tier not in TIERS:
            console.print(f"[red]Unknown tier {tier!r}.[/red] One of: {', '.join(TIERS)}")
        else:
            _run_checks(console, hub, tier, rest[1:], info)
    elif cmd == "debug":
        _set_debug(console, on=(rest[:1] or ["on"])[0].lower() != "off")
    else:
        console.print(f"[red]Unknown command {cmd!r}.[/red] Type 'help'.")
    return info


def main() -> None:
    ap = argparse.ArgumentParser(description="Interactive checkup for a Tiger controller.")
    ap.add_argument("--port", default="COM3", help="Serial port (default: COM3)")
    ap.add_argument("--check", action="store_true", help="Run the read tier and exit")
    ap.add_argument("--debug", action="store_true", help="Log raw frames, which shows retries")
    args = ap.parse_args()

    console = Console()
    if args.debug:
        _set_debug(console, on=True)

    hub = TigerHub(args.port)
    try:
        info = hub.box.info()
        console.print(header_panel(args.port, info, hub.box.current_mode()))

        if args.check:
            _run_checks(console, hub, "read", [], info)
            return

        console.print(axes_table(hub, info))
        console.print(Panel(HELP, border_style="grey50", expand=False))

        while True:
            console.print()
            try:
                raw = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not raw:
                continue
            cmd, *rest = raw.split()
            if cmd.lower() in ("quit", "q", "exit"):
                break
            info = _handle(console, hub, info, args.port, cmd.lower(), rest)
    finally:
        hub.close()


if __name__ == "__main__":
    main()
