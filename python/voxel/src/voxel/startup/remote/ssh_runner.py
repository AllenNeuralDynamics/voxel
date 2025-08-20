from pathlib import Path
from plumbum import local
from voxel.startup.remote.server import INodeServerRunner

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voxel.startup.config import RemoteNodeConfig


def rsync_repo(local_path: Path, remote_path: str, config: "RemoteNodeConfig") -> None:
    ssh_key = config.ssh_key or "id_voxel2"
    key_path = Path.home() / ".ssh" / ssh_key

    user = config.ssh_user or "walter.mwaniki"
    host = config.host
    port = str(config.ssh_port or 22)

    # Build the ssh "transport" once; Plumbum will handle quoting
    ssh_cmd = local["ssh"][
        "-i",
        str(key_path),
        "-p",
        port,
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
    ]

    ignore_patterns = [".git", ".venv", ".voxel", ".vscode", "__pycache__", ".DS_Store"]
    exclude_args = [arg for pat in ignore_patterns for arg in ("--exclude", pat)]

    src = f"{local_path.as_posix().rstrip('/')}/"  # trailing slash => copy contents
    dst = f"{user}@{host}:{remote_path.rstrip('/')}/"

    rsync = local["rsync"][
        "-az",
        "--delete",
        *exclude_args,
        "-e",
        str(ssh_cmd),  # nest the ssh command as a single argument
        src,
        dst,
    ]

    print(f"[rsync] {rsync}")
    rc, out, err = rsync.run(retcode=None)  # returns (rc, stdout, stderr)
    if rc != 0:
        raise RuntimeError(f"rsync failed (rc={rc}): {err.strip()}")


class SSHServerRunner(INodeServerRunner):
    LOCAL_REPO_PATH = Path(__file__).parent.parent.parent.parent
    REMOTE_REPO_PATH = "~/.voxel/service/voxel2"

    def __init__(self, uid: str, config: "RemoteNodeConfig"):
        super().__init__(uid, config)
        self._pidfile: str = f"{self.REMOTE_REPO_PATH}/{uid}.pid"

    def start(self) -> None:
        if not self._config.ssh_user or not self._config.ssh_key:
            raise RuntimeError("SSH user or key not configured")

        user = self._config.ssh_user
        host = self._config.host
        port = str(self._config.ssh_port or 22)
        key = Path.home() / ".ssh" / self._config.ssh_key

        ssh = local["ssh"][
            "-i",
            str(key),
            "-p",
            port,
            "-o",
            "BatchMode=yes",
            "-o",
            "PasswordAuthentication=no",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            f"{user}@{host}",
        ]

        shell = "zsh"  # or "bash"
        # Everything after -lc must be ONE argument; Plumbum will pass it as such
        remote_script = (
            f"cd {self.REMOTE_REPO_PATH} && "
            f"uv sync && "
            f"uv run voxel-remote --uid {self._uid} --port {self._config.rpc_port} "
            f">> {self.REMOTE_REPO_PATH}/{self._uid}.log 2>&1 & "
            f"echo $! > {self._pidfile}"
        )

        cmd = ssh[shell, "-lc", remote_script]
        print(f"[ssh-launch] {cmd}")
        rc, out, err = cmd.run(retcode=None)
        if rc != 0:
            raise RuntimeError(f"remote start failed (rc={rc}): {err.strip()}")

    def sync(self) -> None:
        rsync_repo(
            local_path=self.LOCAL_REPO_PATH,
            remote_path=self.REMOTE_REPO_PATH,
            config=self._config,
        )

    def stop(self) -> None:
        if not self._pidfile:
            return
        if not self._config.ssh_user or not self._config.ssh_key:
            raise RuntimeError("SSH user or key not configured")

        user = self._config.ssh_user
        host = self._config.host
        port = str(self._config.ssh_port or 22)
        key = Path.home() / ".ssh" / self._config.ssh_key

        ssh = local["ssh"][
            "-i",
            str(key),
            "-p",
            port,
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            f"{user}@{host}",
        ]

        remote = f"kill $(cat {self._pidfile}) && rm -f {self._pidfile}"
        cmd = ssh["bash", "-lc", remote]
        print(f"[ssh-stop] {cmd}")
        cmd.run(retcode=None)  # ignore rc; or check and raise like above
