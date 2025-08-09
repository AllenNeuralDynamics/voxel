import logging
import subprocess
import time
from pathlib import Path


class Memento:
    """Class for handling Memento logging."""

    def __init__(self, path: Path, memento_exe_path: Path):
        """
        Initialize the Memento object.

        :param path: Path to save the Memento logs
        :type path: Path
        :param memento_exe_path: Path to the Memento executable
        :type memento_exe_path: Path
        :raises FileNotFoundError: If the Memento executable or output path does not exist
        """
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.path = path
        self.memento_path = memento_exe_path
        self.cmd = None
        if not self.memento_path.exists():
            self.log.error("memento executable path does not exist.")
        if not self.path.exists():
            error = "memento output destination path " f"{str(self.path)} cannot be found."
            self.log.error(error)
            raise FileNotFoundError(error)

    def start(self, filename: str) -> None:
        """
        Start the Memento logging process.

        :param filename: Filename for the Memento log
        :type filename: str
        """
        if not self.memento_path.exists():
            self.log.error("aborting start. cannot find memento executable.")
            return
        cmd_text = f"{str(self.memento_path)} dump " f"--output={str(self.path)}\\{filename}.memento --follow"
        self.cmd = subprocess.Popen(cmd_text)
        time.sleep(1)  # takes time for memento to boot sometimes

    def stop(self) -> None:
        """
        Stop the Memento logging process.
        """
        if not self.memento_path.exists():
            self.log.error("aborting stop. cannot find memento executable.")
            return
        # Terminate the memento subprocess.
        subprocess.call(["taskkill", "/F", "/T", "/PID", str(self.cmd.pid)])
        self.cmd.wait()

    def close(self) -> None:
        """
        Close the Memento logging process.
        """
        if not self.memento_path.exists():
            self.log.error("aborting close. no memento log was created.")
            return
        self.cmd.terminate()
