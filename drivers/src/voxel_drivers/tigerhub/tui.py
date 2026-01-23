"""TigerBox Safe TUI (read-only).

Axis view blends:
  • Overview (card/slot/id/enc, pos, busy, joystick)
  • Motion & limits (speed, accel, backlash, home, limits, control, counts/mm)
  • PID + home speed
  • Status bits from AxisState (limit hits, homed, loop enabled, errors…)

Plus:
  • Cards & Modules (on demand)

Commands:
  list              - list detected axes
  show X            - show details for axis X (e.g., show A)
  next / prev       - cycle through axes
  refresh           - refresh info/positions/busy/joystick
  cards             - show Cards & Modules compact table
  help              - show help
  quit / q          - exit

Safe: performs no moves / homes / writes.
"""

import argparse
from collections.abc import Mapping
from typing import Any

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from voxel_drivers.tigerhub.box import TigerBox
from voxel_drivers.tigerhub.model.box_info import BoxInfo
from voxel_drivers.tigerhub.ops.joystick import JoystickInput
from voxel_drivers.tigerhub.ops.params import TigerParams

# ---------------- UI bits ---------------- #


def _dot_busy(is_moving: bool) -> Text:
    return Text("●", style="green") if is_moving else Text("·", style="dim")


def _kv_grid() -> Table:
    g = Table.grid(padding=(0, 1))
    g.add_column(justify="left", style="bold")
    g.add_column(justify="right", style="cyan")
    return g


def header_panel(*, port: str, version: str | None, mode: str | None) -> Panel:
    g = _kv_grid()
    g.add_row("Port", port)
    g.add_row("Version", version or "—")
    g.add_row("Mode", mode or "—")
    return Panel(g, title="[bold]TigerBox Safe TUI[/bold]", border_style="yellow", padding=(0, 1), expand=False)


def cards_table(info: BoxInfo) -> Table:
    t = Table(box=box.SIMPLE, show_lines=False, expand=True, pad_edge=False)
    t.add_column("Card", justify="right", style="bold")
    t.add_column("Board")
    t.add_column("FW", style="cyan")
    t.add_column("Date", style="cyan")
    t.add_column("Flags", style="cyan")
    t.add_column("Modules", style="green")
    for c in info.cards:
        t.add_row(
            f"0x{c.addr:X}",
            str(c.board),
            str(c.fw),
            str(c.date),
            str(c.flags) if c.flags else "—",
            ", ".join(sorted(c.mods)) or "—",
        )
    return t


# ---------------- Axis detail ---------------- #


def _axis_state_bits(axis_state_obj: Any) -> dict[str, Any]:
    """Extract useful status bits from AxisState safely.
    We keep names short and only add rows that exist.
    """
    # try a bunch of common names, fallback to None if missing
    g = {}

    def grab(out_key: str, *candidates: str):
        for name in candidates:
            if hasattr(axis_state_obj, name):
                g[out_key] = getattr(axis_state_obj, name)
                return
        g[out_key] = None

    grab("Limit Min Hit", "limit_min_hit", "at_min", "min_limit_hit", "limit_low_hit")
    grab("Limit Max Hit", "limit_max_hit", "at_max", "max_limit_hit", "limit_high_hit")
    grab("Homed", "homed", "is_homed")
    grab("Closed Loop", "closed_loop", "servo_on", "servo_enabled", "in_closed_loop")
    grab("Motor On", "motor_on", "motor_enabled")
    grab("Error", "error", "fault", "error_code")

    # prune Nones so we don't add junk rows
    return {k: v for k, v in g.items() if v is not None}


def axis_detail_panel(
    uid: str,
    info: BoxInfo,
    pos: Mapping[str, float],
    busy: Mapping[str, bool],
    jmap: Mapping[str, JoystickInput],
    speed: Mapping[str, float],
    accel: Mapping[str, float],
    bkl: Mapping[str, float],
    home: Mapping[str, float],
    llo: Mapping[str, float],
    lhi: Mapping[str, float],
    ctrl: Mapping[str, int],
    cnts: Mapping[str, float],
    pid_p: Mapping[str, float],
    pid_i: Mapping[str, float],
    pid_d: Mapping[str, float],
    hspd: Mapping[str, float],
    axis_state_obj: Any,
) -> Panel:
    """Single, compact panel that merges AxisState status bits into the axis card.
    (We avoid duplicating pos/limits/backlash which already appear via params/where.).
    """
    ax = info.axes[uid]

    left = _kv_grid()
    # Overview
    left.add_row("Card", f"0x{ax.card_hex:X}" if ax.card_hex is not None else "—")
    left.add_row("Slot", str(ax.card_index) if ax.card_index is not None else "—")
    left.add_row("Axis ID", str(ax.axis_id) if ax.axis_id is not None else "—")
    left.add_row("Enc/mm", f"{ax.enc_cnts_per_mm:.3f}" if ax.enc_cnts_per_mm is not None else "—")
    left.add_row("Pos", f"{pos.get(uid, '—')}")
    left.add_row("Busy", _dot_busy(busy.get(uid, False)))
    left.add_row("Joy", str(jmap.get(uid, "—")))

    # Motion & limits (typed params)
    left.add_row("Speed", f"{speed.get(uid, '—')}")
    left.add_row("Accel", f"{accel.get(uid, '—')}")
    left.add_row("Backlash", f"{bkl.get(uid, '—')}")
    left.add_row("Home", f"{home.get(uid, '—')}")
    left.add_row("Limit Low", f"{llo.get(uid, '—')}")
    left.add_row("Limit High", f"{lhi.get(uid, '—')}")
    left.add_row("Control", f"{ctrl.get(uid, '—')}")
    left.add_row("Counts/mm", f"{cnts.get(uid, '—')}")

    # PID
    left.add_row("PID P", f"{pid_p.get(uid, '—')}")
    left.add_row("PID I", f"{pid_i.get(uid, '—')}")
    left.add_row("PID D", f"{pid_d.get(uid, '—')}")
    left.add_row("Home Spd", f"{hspd.get(uid, '—')}")

    # AxisState status bits (non-overlapping, compact)
    bits = _axis_state_bits(axis_state_obj)
    if bits:
        left.add_row("—", "—")  # thin separator
        for k, v in bits.items():
            left.add_row(k, str(v))

    return Panel(left, title=f"[bold white]Axis {uid}[/bold white]", border_style="cyan", padding=(0, 1), expand=True)


# -------------- data helpers -------------- #


def refresh_snapshot(
    drv: TigerBox,
) -> tuple[BoxInfo, list[str], dict[str, float], dict[str, bool], dict[str, JoystickInput]]:
    info = drv.info(refresh=True)
    axes = sorted(info.axes.keys())
    pos = drv.get_position(axes) if axes else {}
    busy = drv.is_axis_moving(axes) if axes else {}
    jmap = drv.get_joystick_mapping(refresh=True)
    return info, axes, pos, busy, jmap


def fetch_axis_params(drv: TigerBox, uid: str) -> Mapping[str, Mapping[str, Any]]:
    axlist = [uid]
    return {
        "speed": drv.get_param(TigerParams.SPEED, axlist),
        "accel": drv.get_param(TigerParams.ACCEL, axlist),
        "bkl": drv.get_param(TigerParams.BACKLASH, axlist),
        "home": drv.get_param(TigerParams.HOME_POS, axlist),
        "llo": drv.get_param(TigerParams.LIMIT_LOW, axlist),
        "lhi": drv.get_param(TigerParams.LIMIT_HIGH, axlist),
        "ctrl": drv.get_param(TigerParams.CONTROL_MODE, axlist),
        "cnts": drv.get_param(TigerParams.ENCODER_CNTS, axlist),
        "pid_p": drv.get_param(TigerParams.PID_P, axlist),
        "pid_i": drv.get_param(TigerParams.PID_I, axlist),
        "pid_d": drv.get_param(TigerParams.PID_D, axlist),
        "hspd": drv.get_param(TigerParams.HOME_SPEED, axlist),
    }


def build_axis_panel(
    drv: TigerBox,
    info: BoxInfo,
    pos: Mapping[str, float],
    busy: Mapping[str, bool],
    jmap: Mapping[str, JoystickInput],
    uid: str,
) -> Panel:
    """Fetch read-only params/state for one axis and return a Panel (no printing)."""
    uid = uid.upper()
    axis_state = drv.get_axis_state(uid)
    params = fetch_axis_params(drv, uid)
    return axis_detail_panel(
        uid,
        info,
        pos,
        busy,
        jmap,
        params["speed"],
        params["accel"],
        params["bkl"],
        params["home"],
        params["llo"],
        params["lhi"],
        params["ctrl"],
        params["cnts"],
        params["pid_p"],
        params["pid_i"],
        params["pid_d"],
        params["hspd"],
        axis_state_obj=axis_state,
    )


def render_axis_view(
    console: Console,
    drv: TigerBox,
    info: BoxInfo,
    axes: list[str],
    pos: Mapping[str, float],
    busy: Mapping[str, bool],
    jmap: Mapping[str, JoystickInput],
    uid: str,
) -> None:
    del axes  # not needed here
    uid = uid.upper()
    if uid not in info.axes:
        console.print(f"[red]Unknown axis:[/red] {uid}")
        return
    console.print(build_axis_panel(drv, info, pos, busy, jmap, uid))


def print_help(console: Console) -> None:
    help_str = (
        "[bold]Commands[/bold]\n"
        "  list             List detected axes\n"
        "  show X           Show details for axis X (e.g., show A)\n"
        "  next / prev      Cycle to next/previous axis\n"
        "  refresh          Refresh info/positions/busy/joystick\n"
        "  cards            Show Cards & Modules\n"
        "  help             This help\n"
        "  quit / q         Exit"
    )
    console.print(Panel(help_str, title="[bold]Help[/bold]", border_style="grey50", expand=False))


# ---------------- main loop ---------------- #


def main() -> None:  # noqa: C901, PLR0915 - TUI main loop
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM3", help="Serial port (default: COM3)")
    args = ap.parse_args()

    console = Console()

    def print_all_multiple_axes(axes: list[str]):
        panels = [build_axis_panel(drv, info, pos, busy, jmap, axis) for axis in axes]
        console.print(Columns(panels, expand=False, equal=True, padding=(0, 1)))

    drv = TigerBox(port=args.port)
    try:
        info, axes, pos, busy, jmap = refresh_snapshot(drv)

        console.print(
            header_panel(
                port=args.port,
                version=info.version,
                mode=str(drv.current_mode()) if drv.current_mode() is not None else None,
            ),
        )

        if axes:
            console.print(Panel(f"Detected axes: [bold]{', '.join(axes)}[/bold]", border_style="cyan", expand=False))
        else:
            console.print(Panel("No axes detected.", border_style="cyan", expand=False))

        print_help(console)

        idx = 0 if axes else -1
        if idx >= 0:
            print_all_multiple_axes(axes)

        while True:
            axes_hint = f"  [dim]Axes: {', '.join(axes)}[/dim]" if axes else ""
            console.print(f"\nType a command (help for options).{axes_hint}")
            cmd = input("> ").strip()

            if not cmd:
                continue
            cl = cmd.lower()

            if cl in ("quit", "q"):
                break

            if cl == "help":
                print_help(console)
                continue

            if cl == "list":
                info = drv.info(refresh=False)
                axes = sorted(info.axes.keys())
                console.print(
                    Panel(
                        f"Detected axes: [bold]{', '.join(axes) if axes else '—'}[/bold]",
                        border_style="cyan",
                        expand=False,
                    ),
                )
                if axes and idx == -1:
                    idx = 0
                continue

            if cl in ("next", "prev"):
                if not axes:
                    console.print("[red]No axes to cycle.[/red]")
                    continue
                idx = (idx + (1 if cl == "next" else -1)) % len(axes)
                render_axis_view(console, drv, info, axes, pos, busy, jmap, axes[idx])
                continue

            if cl == "refresh":
                info, axes, pos, busy, jmap = refresh_snapshot(drv)
                console.print(Panel("Refreshed.", border_style="green", expand=True))
                if axes:
                    if idx == -1:
                        idx = 0
                    else:
                        idx %= len(axes)
                    render_axis_view(console, drv, info, axes, pos, busy, jmap, axes[idx])
                else:
                    idx = -1
                continue

            if cl == "cards":
                console.print(
                    Panel(
                        cards_table(info),
                        title="[bold yellow]Cards & Modules[/bold yellow]",
                        border_style="yellow",
                        padding=(0, 1),
                    ),
                )
                continue

            if cl.startswith("show"):
                parts = cmd.split()
                # No args: show all axes (horizontally)
                if len(parts) == 1:
                    if not axes:
                        console.print("[red]No axes detected.[/red]")
                        continue
                    print_all_multiple_axes(axes)
                    continue

                # One or more axes requested: validate, ignore invalid, horizontal layout
                req_axes = [p.upper() for p in parts[1:]]
                valid_axes = [a for a in req_axes if a in info.axes]
                invalid_axes = [a for a in req_axes if a not in info.axes]

                if invalid_axes:
                    console.print(f"[yellow]Ignoring unknown axes:[/yellow] {', '.join(invalid_axes)}")

                if not valid_axes:
                    console.print("[red]No valid axes to show.[/red]")
                    continue

                # Build panels for valid axes and display side-by-side
                panels = [build_axis_panel(drv, info, pos, busy, jmap, axis) for axis in valid_axes]
                console.print(Columns(panels, equal=True, expand=True, padding=(0, 1), align="left"))

                # Update cursor to last requested valid axis so next/prev feel natural
                if axes:
                    try:
                        idx = axes.index(valid_axes[-1])
                    except ValueError:
                        # If axes list changed, refresh snapshot and try again silently
                        info, axes, pos, busy, jmap = refresh_snapshot(drv)
                        if valid_axes[-1] in axes:
                            idx = axes.index(valid_axes[-1])
                continue

            console.print("[red]Unknown command.[/red] Type 'help' for options.")

    finally:
        drv.close()


if __name__ == "__main__":
    main()
