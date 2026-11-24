# Children that outlive the station

Researched and prototyped on 2026-11-21. Not built. Asked for in `server.md` › Decided on 2026-11-21. Try-outs in
`prototypes/orphans/`.

## The problem

When the station process is killed hard (SIGKILL, a crash, Windows TerminateProcess), nothing ends its children.

**Without `nodes:`**, `Rig` puts every device in the station's own process (`LocalNode`, `rigup/src/rigup/rig.py` › `_create_nodes`). The station then has 2 kinds of
child:

| Child | Started by | What it holds |
| --- | --- | --- |
| the server (`python -m vxl.web.server`) | `StationRun` (`src/vxl/cli/station.py`) | port 8000; windows see old data |
| a writer worker, and the multiprocessing resource tracker | the camera's controller, through `OMEZarrWriter` (`src/vxl/devices/camera/area.py`), which makes `BatchSlot`s (`omezarr/src/ome_zarr_writer/slot.py`): a `ProcessPoolExecutor` with the spawn context | shared memory, made with `track=False`: up to hundreds of GB |

**Only with `nodes:` in a rig file.** Of the templates, only `z-step-4-nodes.yaml` has them: 1 `subprocess` node
per camera. No instrument in `~/.voxel/instruments` has them.

- A `subprocess` node is 1 more child of the station (`python -m rigup.node`, `SubprocessNode`). A writer worker is
  then a child of the node that runs the camera, not of the station.
- A `remote` node runs on another computer (`vxl node start`, `serve_node`). It is not a child of the station, and it
  is meant to keep running between stations: `RemoteNode.close()` closes its devices and releases its claim, and
  leaves the process running.

Legacy had the same, except the server: its web app ran in the station process. `omezarr/scripts/cleanup_shm.py`
exists for the shared memory that crashes left.

## What the try-outs show

macOS, CPython 3.13.

**`today.py`**: a stand-in station starts each kind of child, and is killed with SIGKILL. 60 s later, all 4 children
still run: the server (it still answers on its port), the rigup node, the writer worker and the resource tracker. The
shared memory is still there.

Why the writer worker and the tracker stay: a pool worker waits on its call queue, and the queue gives the child
both ends of its pipe, so the worker never sees end of file. The tracker waits for end of file on a pipe that the
worker also holds.

**Seen on a real run** (2026-11-23, `z-step-4-nodes.yaml`, a SIGKILL of the `camera_2` node during a scan): the
node's 4 writer workers and its resource tracker kept running with parent 1 after the station closed. They also
kept the station's stdout and stderr open, so a shell pipe that read the station's output did not end until they
were stopped by hand.

**`ways.py`**: 4 ways for a child to notice that its parent died, after a SIGKILL of the parent:

| Way | Noticed after | Systems |
| --- | --- | --- |
| End of file on a stdin pipe | 0.001 s | macOS, Linux, Windows |
| Poll the parent's id, every 1 s, against the first parent | 0.5 s | macOS, Linux; not Windows |
| The OS's notice (kqueue `NOTE_EXIT`) | 0.002 s | macOS, BSD only; Linux has `PR_SET_PDEATHSIG` instead |
| The parent's sentinel (`multiprocessing.parent_process().sentinel`) | 0.002 s | macOS, Linux, Windows; multiprocessing children only |

- A sibling started after the stdin child does not keep the pipe open: `subprocess` and asyncio close other file
  descriptors in a child by default.
- **The stdin way needs a flag.** With an empty stdin, as a service manager gives a program, the child ends at once
  although its parent lives.

**`zmq_watch.py`**: a node binds a ROUTER, as `ZMQTransportServer` does, and watches it with a ZMQ socket monitor
(`EVENT_ACCEPTED`, `EVENT_DISCONNECTED`). A station connects a DEALER, as `ZMQTransportClient` does, and is killed
with SIGKILL. The node saw the disconnect 0.001 s later, over TCP and over IPC. No heartbeat is needed: the OS closes
the dead process's sockets. A computer that loses power or its network sends nothing; then rigup's TCP keepalive
(1 s idle, 1 s interval, 3 tries, on both sides) shows it after about 4 s.

**A remote node refuses every new station after a hard kill** (checked on 2026-11-21 with `vxl node start` and 3
stations in a row). The node keeps the claim of the dead station (`NodeDaemon._authority_owner`), and each station
claims with a new id (`RemoteNode`: `rig-{id(self):x}`). Station 2 and station 3 got "Authority claim rejected for
node lasers (current owner: rig-…)". Only a restart of the node by hand clears it. A normal close of a station
releases the claim, so this happens only after a crash.

## What others do

- **Poll the parent's id:** Jupyter's kernel on Unix, once a second. It compared with 1 until 2024; on modern Linux
  an orphan goes to a systemd user process instead, so it now compares with the first parent
  ([ipykernel PR #1271](https://gh.ali360.cloudns.ch/ipython/ipykernel/pull/1271)). On Windows `os.getppid` keeps the dead
  parent's id (Python docs), so Jupyter waits on a process handle that the launcher passes
  ([parentpoller.py](https://gh.ali360.cloudns.ch/ipython/ipykernel/blob/main/ipykernel/parentpoller.py),
  [launcher.py](https://gh.ali360.cloudns.ch/jupyter/jupyter_client/blob/main/jupyter_client/launcher.py)).
- **End of file on stdin:** Erlang ports ([port tutorial](https://www.erlang.org/doc/system/c_port.html)), and
  language servers: Microsoft's library exits when its input ends, and also polls the editor's process id
  ([LSP spec, `processId`](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/),
  [vscode-languageserver-node](https://gh.ali360.cloudns.ch/microsoft/vscode-languageserver-node/blob/main/server/src/node/main.ts)).
- **The parent's sentinel:** every spawn child of multiprocessing has one (Python 3.8 and later). Nothing acts on it
  by itself; the child must watch it
  ([multiprocessing docs](https://docs.python.org/3.13/library/multiprocessing.html),
  [spawn.py](https://gh.ali360.cloudns.ch/python/cpython/blob/3.13/Lib/multiprocessing/spawn.py)).
- **The OS's own way:** QEMU's `exit-with-parent` uses `PR_SET_PDEATHSIG` on Linux and kqueue on macOS
  ([exit-with-parent.c](https://qemu.googlesource.com/qemu/+/refs/heads/master/system/exit-with-parent.c)).
  `PR_SET_PDEATHSIG` fires when the parent *thread* ends
  ([man page](https://man7.org/linux/man-pages/man2/pr_set_pdeathsig.2const.html)).
- **A Windows job object:** with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, every process in the job ends when the last
  handle to it closes, children of children included
  ([job objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
  [limit flags](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information)).
  Cargo puts itself in such a job at start, so every later child is in it
  ([cargo job.rs](https://doc.rust-lang.org/stable/nightly-rustc/src/cargo/util/job.rs.html)). Python has no
  public API for it; `ctypes` or pywin32 can do it.
- **Service managers** clean up only when the station runs as a service:
  - systemd kills every process of the unit's control group when the unit stops, also after its main process died
    (`KillMode=control-group`, the default)
    ([systemd.kill](https://www.freedesktop.org/software/systemd/man/latest/systemd.kill.html)).
  - launchd kills the remaining processes of the job's process group
    ([launchd.plist, `AbandonProcessGroup`](https://keith.github.io/xcode-man-pages/launchd.plist.5.html)).
  - NSSM ends the application and its subprocesses on stop ([NSSM usage](https://nssm.cc/usage)). WinSW can leak
    the tree when it is killed itself, and has an extension that kills it at the next start
    ([RunawayProcessKiller](https://gh.ali360.cloudns.ch/winsw/winsw/blob/master/doc/extensions/runawayProcessKiller.md)).
- supervisord's `stopasgroup` and `killasgroup` act only when supervisord stops a program
  ([configuration](https://supervisord.org/configuration.html)). tini is for containers
  ([tini](https://gh.ali360.cloudns.ch/krallin/tini)).

## Picks

My judgment, from the try-outs and the sources above.

| Child | Way | Why |
| --- | --- | --- |
| the server | end of file on stdin, with an opt-in flag; `StationRun` keeps a pipe on its stdin | every system; 0.001 s; any server program, in any language, can do it |
| a rigup device node | the node watches its ROUTER with a ZMQ socket monitor. When no peer is left: a subprocess node shuts down cleanly (as on SIGTERM); a remote node releases its claim after a short grace time and keeps running | every system; covers both kinds of node and the claim bug; no flag, no heartbeat; 0.001 s, or about 4 s for a lost network |
| a writer worker | a thread in `_worker_init` waits on the parent's sentinel, then unlinks the slot's shared memory and exits | stdlib; every system; frees the memory that a crash leaves today |
| the resource tracker | nothing: it ends when the workers end, as they hold its pipe | to check when this is built |

- Rejected: polling the parent's id (it fails on Windows, and reacts 0.5 s late on average), and the OS's own ways
  (different code for each system, and none on Windows).
- Later, if a child of some library does not watch its parent on Windows: the station puts itself in a
  kill-on-close job at start, as Cargo does. About 30 lines of `ctypes`; it cannot be tested on this Mac.
- On a real rig, run `vxl station start` under the OS service manager: it restarts the station after a crash, and
  systemd and launchd also clean up the children.

## Open

- **Names:** the flag of the server. QEMU says `exit-with-parent`. The rigup node needs no flag.
- **The remote node's grace time,** so a short network drop does not cost the station its claim: ZMQ connects again
  by itself. A refused second station that disconnects must not release the owner's claim; counting the peers that
  are still connected covers that.
- **Windows:** 1 run of `today.py` and `ways.py` on a Windows computer. `ways.py` uses kqueue, which Windows does not
  have; that way must be skipped there.
- **`uv run` adds a process:** with `uv run vxl station start`, a SIGKILL of the `uv` process leaves the station
  running (seen by the research, on macOS). A terminal that closes sends SIGHUP to both, which is fine.
- The changes touch 2 packages outside `src/vxl`: `rigup/` (the node) and `omezarr/` (the writer).
