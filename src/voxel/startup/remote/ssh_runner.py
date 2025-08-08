from pathlib import Path
from plumbum import local

from voxel.startup.remote.server import INodeServerRunner

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voxel.startup.config import RemoteNodeConfig


def rsync_repo(local_path: Path, remote_path: str, config: "RemoteNodeConfig") -> None:
    ssh_key = config.ssh_key or "id_voxel2"

    # 1) Build absolute key path
    key_path = Path.home() / ".ssh" / ssh_key

    # 2) SSH connection params
    user = config.ssh_user or "walter.mwaniki"
    host = config.host
    port = config.ssh_port or 22

    # 3) SSH options: only key auth, no password prompts
    ssh_opts = (
        f"-i {key_path} "
        f"-p {port} "
        "-o BatchMode=yes "
        "-o PasswordAuthentication=no "
        "-o StrictHostKeyChecking=no "
        "-o UserKnownHostsFile=/dev/null"
    )

    # 4) Exclude typical dev dirs/files
    ignore_patterns = [".git", ".venv", ".voxel", ".vscode", "__pycache__", ".DS_Store"]
    ignore_args = " ".join(f"--exclude='{pat}'" for pat in ignore_patterns)

    # 5) Assemble and run rsync
    rsync_cmd = (
        f'rsync -az --delete {ignore_args} -e "ssh {ssh_opts}" {local_path.as_posix()}/ {user}@{host}:{remote_path}/'
    )
    print(f"[rsync] {rsync_cmd}")
    local(rsync_cmd, hide=True, warn=True)


class SSHServerRunner(INodeServerRunner):
    LOCAL_REPO_PATH = Path(__file__).parent.parent.parent.parent
    REMOTE_REPO_PATH = "~/.voxel/service/voxel2"

    def __init__(self, uid: str, config: "RemoteNodeConfig"):
        super().__init__(uid, config)
        self._pidfile: str = f"{self.REMOTE_REPO_PATH}/{uid}.pid"

    def start(self) -> None:
        """
        SSH in, run uv sync + uv run under a login shell,
        background the process, write its PID to <dest>/<uid>.pid,
        return that pidfile path.
        """
        if not self._config.ssh_user or not self._config.ssh_key:
            print("SSH user or key not configured, cannot start remote server.")
            raise RuntimeError("SSH user or key not configured")

        host = self._config.host
        user = self._config.ssh_user
        port = self._config.ssh_port or 22
        key = Path.home() / ".ssh" / self._config.ssh_key

        ssh_opts = f"-i {key} -p {port} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
        ssh_base = f"ssh {ssh_opts} {user}@{host}"

        # wrap uv calls in bash -lc so ~/.local/bin is on PATH
        shell = "zsh"
        launch = (
            f"cd {self.REMOTE_REPO_PATH} && "
            f"{shell} -lc 'uv sync && "
            f"uv run voxel-remote --uid {self._uid} --port {self._config.rpc_port} "
            f">> {self.REMOTE_REPO_PATH}/{self._uid}.log 2>&1 & "
            "echo $! > " + self._pidfile + "'"
        )

        full_cmd = f'{ssh_base} "{launch}"'
        print(f"[ssh-launch] {full_cmd}")
        local(full_cmd, hide=True, warn=False)  # warn=False → propagate failures

    def sync(self) -> None:
        rsync_repo(
            local_path=self.LOCAL_REPO_PATH,
            remote_path=self.REMOTE_REPO_PATH,
            config=self._config,
        )

    def stop(self) -> None:
        """
        Kill the remote process based on the stored pidfile.
        """
        if not self._pidfile:
            return
        if not self._config.ssh_user or not self._config.ssh_key:
            print("SSH user or key not configured, cannot stop remote server.")
            raise RuntimeError("SSH user or key not configured")

        host = self._config.host
        user = self._config.ssh_user
        port = self._config.ssh_port or 22
        key = Path.home() / ".ssh" / self._config.ssh_key

        ssh_opts = f"-i {key} -p {port} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
        ssh_base = f"ssh {ssh_opts} {user}@{host}"

        stop = f"kill $(cat {self._pidfile}) && rm {self._pidfile}"
        full = f'{ssh_base} "{stop}"'
        print(f"[ssh-stop] {full}")
        local(full, hide=True, warn=True)
