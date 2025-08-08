import os
import shutil
import time
from pathlib import Path
from subprocess import DEVNULL, Popen

from voxel_classic.file_transfers.base import BaseFileTransfer


class RobocopyFileTransfer(BaseFileTransfer):
    """
    Voxel driver for Robocopy file transfer process.

    Process will transfer files with the following regex
    format:

    From -> \\\\local_path\\\\acquisition_name\\\\filename*
    To -> \\\\external_path\\\\acquisition_name\\\\filename*
    """

    def __init__(self, external_path: str, local_path: str):
        """
        Initialize the RobocopyFileTransfer class.

        :param external_path: The external path of files to be transferred.
        :type external_path: str
        :param local_path: The local path of files to be transferred.
        :type local_path: str
        """
        super().__init__(external_path, local_path)
        self._protocol = "robocopy"
        self._threads = 8  # default to 8 threads

    @property
    def threads(self) -> int:
        """
        Get the number of threads to use for the file transfer process.

        :return: The number of threads to use for the file transfer process.
        :rtype: int
        """
        return self._threads

    @threads.setter
    def threads(self, num_threads: int) -> None:
        """
        Set the number of threads to use for the file transfer process.

        :param num_threads: The number of threads to use for the file transfer process.
        :type num_threads: int
        """
        self._threads = num_threads

    def _run(self) -> None:
        """
        Run the file transfer process.

        :raises ValueError: If the local file path is not a file or directory.
        """
        start_time = time.time()
        local_directory = Path(self._local_path, self._acquisition_name)
        external_directory = Path(self._external_path, self._acquisition_name)
        transfer_complete = False
        retry_num = 0
        # loop over number of attempts in the event that a file transfer fails
        while transfer_complete is False and retry_num <= self._max_retry - 1:
            # generate a list of files or directories to copy
            file_list = []
            for name in os.listdir(local_directory.absolute()):
                if self.filename in name:
                    file_list.append(name)
            # if file list is empty, transfer must be complete
            if not file_list:
                transfer_complete = True
            # if not, try to initiate transfer again
            else:
                num_files = len(file_list)
                self.log.info(f"attempt {retry_num+1}/{self._max_retry}, transferring {num_files} files.")
                for file_path in file_list:
                    self.log.info(f"transfering {file_path}")
                    # check if file is a zarr store
                    if ".zarr" in file_path:
                        local_dir = str(Path(local_directory, Path(file_path)))
                        external_dir = str(Path(external_directory, Path(file_path)))
                        # robocopy flags
                        # /j unbuffered copy for transfer speed stability
                        # /mir mirrors directory tree
                        # /mt:N multi-threaded copy with N threads
                        log_path = Path(local_directory, f"{self._filename}_zarr.log")
                        cmd_with_args = f"{self._protocol} {local_dir} {external_dir} \
                            /j /mir /mt:{self.threads} /log:{log_path}"
                        subprocess = Popen(cmd_with_args, stdout=DEVNULL)
                        time.sleep(1.0)
                        subprocess.wait()
                        self.log.info(f"{file_path} transfer is complete.")
                    else:
                        # robocopy flags
                        # /j unbuffered copy for transfer speed stability
                        # /mov deletes local files after transfer
                        # /if move only the specified filename
                        # /njh no job header in log file
                        # /njs no job summary in log file
                        log_path = Path(local_directory, f"{self._filename}.log")
                        cmd_with_args = f"{self._protocol} {str(local_directory)} {str(external_directory)} \
                            /j /if {file_path} /njh /njs /log:{log_path}"
                        # stdout to PIPE will cause malloc errors on exist
                        # no stdout will print subprocess to python
                        # stdout to DEVNULL will supresss subprocess output
                        subprocess = Popen(cmd_with_args, stdout=DEVNULL)
                        # wait one second for process to start before monitoring log file for progress
                        time.sleep(1.0)
                        subprocess.wait()
                        self.log.info(f"{file_path} transfer is complete.")
                        # clean up and remove the temporary log file
                        os.remove(log_path)
                # clean up the local subdirs and files
                for file_path in file_list:
                    # f is a relative path, convert to absolute
                    local_file_path = os.path.join(local_directory.absolute(), file_path)
                    external_file_path = os.path.join(external_directory.absolute(), file_path)
                    # .zarr is directory but os.path.isdir will return False
                    if os.path.isdir(local_file_path) or ".zarr" in file_path:
                        # TODO how to hash check zarr -> directory instead of file?
                        shutil.rmtree(local_file_path)
                    elif os.path.isfile(local_file_path) and ".log" not in file_path:
                        # verify transfer with hashlib
                        if self._verify_transfer:
                            # put in try except in case no external file found
                            try:
                                # if hash is verified delete file
                                if self._verify_file(local_file_path, external_file_path):
                                    # remove local file
                                    self.log.info(f"deleting {local_file_path}")
                                    os.remove(local_file_path)
                                # if has fails, external file is corrupt
                                else:
                                    # remove external file, try again
                                    self.log.info(f"hashes did not match, deleting {external_file_path}")
                                    os.remove(external_file_path)
                                    pass
                            except FileNotFoundError:
                                self.log.warning(f"no external file exists at {external_file_path}")
                        else:
                            # remove local file
                            self.log.info(f"deleting {local_file_path}")
                            os.remove(local_file_path)
                end_time = time.time()
                total_time = end_time - start_time
                self.log.info(f"{self.filename} transfer complete, total time: {total_time:.2f} [s]")
                subprocess.kill()
                retry_num += 1
