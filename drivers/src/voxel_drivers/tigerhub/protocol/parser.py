from voxel_drivers.tigerhub.model import ASIMode, Reply
from voxel_drivers.tigerhub.protocol.linefmt import _ax


def asi_parse(raw: bytes, requested_axes: list[str] | None = None) -> tuple[Reply, ASIMode]:
    s = (raw or b"").decode(errors="ignore").strip()

    if s.startswith(":N"):
        return Reply("ERR", err=s[2:].strip()), ASIMode.MS2000

    if s.startswith(":A"):
        tail = s[2:].strip()
        if not tail:
            return Reply("ACK"), ASIMode.MS2000
        kv: dict[str, str] = {}
        for tok in tail.split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                kv[_ax(k)] = v.strip()
        if kv:
            if requested_axes:
                ra = {ax.upper() for ax in requested_axes}
                kv = {k: v for k, v in kv.items() if k in ra}
            return Reply("DATA", kv=kv), ASIMode.MS2000
        if requested_axes:
            vals = tail.split()
            kv = {ax.upper(): val for ax, val in zip(requested_axes, vals, strict=False)}
            return Reply("DATA", kv=kv), ASIMode.MS2000
        return Reply("DATA", text=tail), ASIMode.MS2000

    if s == "":
        return Reply("ACK"), ASIMode.TIGER

    # Parse TIGER mode response
    kv = {}
    for tok in s.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            kv[_ax(k)] = v.strip()
    if kv:
        if requested_axes:
            ra = {ax.upper() for ax in requested_axes}
            kv = {k: v for k, v in kv.items() if k in ra}
        return Reply("DATA", kv=kv), ASIMode.TIGER

    return Reply("DATA", text=s), ASIMode.TIGER
