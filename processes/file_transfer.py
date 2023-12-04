"""File Transfer process in a separate class for Win/Linux compatibility."""
import os
import subprocess
import time
from pathlib import Path
from multiprocessing import Process


class FileTransfer(Process):

    def __init__(self, source_path: Path, dest_path: Path, ftp: str,
                 ftp_flags: str = ""):
        super().__init__()
        self.ftp = ftp
        self.ftp_flags = ftp_flags
        self.src_path = source_path
        self.dest_path = dest_path
        self.cmd = None  # handle to the file transfer command that we execute.

    def run(self):
        if not os.path.isfile(self.src_path):
            raise FileNotFoundError(f"{self.src_path} does not exist.")
        # xcopy requires an asterisk to indicate source and destination are
        # files, not directories.
        # TODO: identify if xcopy src/dest are files or directories, and
        #   annotate them as such.
        cmd_with_args = [self.ftp, f'{self.src_path.absolute()}*', f'{self.dest_path.absolute()}*',
                         self.ftp_flags]
        # self.cmd = subprocess.Popen(self.cfg.ftp + ' ' + self.cfg.source_path + tile_name + '* ' + self.cfg.destination_path + ' ' + self.cfg.ftp_flags)
        print(f"Transferring {self.src_path} to storage in {self.dest_path}.")
        self.cmd = subprocess.run(cmd_with_args, check=True)  # blocks.
        # Delete the old file so we don't run out of local storage.
        print(f"Deleting old file at {self.src_path}.")
        os.remove(self.src_path)
        print(f"process finished.")
