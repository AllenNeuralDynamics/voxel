import os
import shutil
import sys
import time
from pathlib import Path
from subprocess import Popen
from typing import Any, Iterable, List

from voxel.file_transfers.base import BaseFileTransfer


class RsyncFileTransfer(BaseFileTransfer):
    """
    Voxel driver for Rsync file transfer process.

    Process will transfer files with the following regex
    format:

    From -> \\\\local_path\\\\acquisition_name\\\\filename*
    To -> \\\\external_path\\\\acquisition_name\\\\filename*

    :param external_path: External path of files to be transferred
    :param local_path: Local path of files to be transferred
    :type external_path: str
    :type local_path: str
    """

    def __init__(self, external_path: str, local_path: str):
        super().__init__(external_path, local_path)
        self._protocol = "rsync"
        # print progress, delete files after transfer
        # check version of rsync
        # tested with v2.6.9
        # --info=progress2 is not available for rsync v2.x.x
        # self._flags = ['--progress', '--remove-source-files', '--recursive']
        # tested with v3.2.7
        # --progress outputs progress which is piped to log file
        # --recursive transfers all files in directory sequentially
        # --info=progress2 outputs % progress for all files not sequentially for each file
        self._flags = ["--progress", "--recursive", "--info=progress2"]

    def _run(self):
        """
        Internal function that runs the transfer process.
        """

        start_time = time.time()
        local_directory = Path(self._local_path, self._acquisition_name)
        external_directory = Path(self._external_path, self._acquisition_name)
        log_path = Path(local_directory, f"{self._filename}.log")
        transfer_complete = False
        retry_num = 0
        # loop over number of attempts in the event that a file transfer fails
        while transfer_complete is False and retry_num <= self._max_retry - 1:
            # generate a list of subdirs and files in the parent local dir to delete at the end
            delete_list = []
            for name in os.listdir(local_directory.absolute()):
                if self.filename in name:
                    delete_list.append(name)
            # generate a list of files to copy
            # path is the entire experiment path
            # subdirs is any tile specific subdir i.e. zarr store
            # files are any tile specific files
            file_list = dict()
            for path, subdirs, files in os.walk(local_directory.absolute()):
                for name in files:
                    # check and only add if filename matches tranfer's filename
                    if self.filename in name and name != log_path:
                        file_list[os.path.join(path, name)] = os.path.getsize(os.path.join(path, name)) / 1024**2
            total_size_mb = sum(file_list.values())
            # sort the file list based on the file sizes and create a list for transfers
            sorted_file_list = dict(sorted(file_list.items(), key=lambda item: item[1]))
            total_transferred_mb = 0
            # if file list is empty, transfer must be complete
            if not sorted_file_list:
                transfer_complete = True
            # if not, try to initiate transfer again
            else:
                self.log.info(f"starting file transfer attempt {retry_num+1}/{self._max_retry}")
                for file_path, file_size_mb in sorted_file_list.items():
                    # transfer just one file and iterate
                    # split filename and path
                    [local_dir, filename] = os.path.split(file_path)
                    self.log.info(f"transfering {filename}")
                    # specify external directory
                    # need to change directories to str because they are Path objects
                    external_dir = local_dir.replace(str(local_directory), str(external_directory))
                    # make external directory tree if needed
                    if not os.path.isdir(external_dir):
                        os.makedirs(external_dir)
                    # setup log file
                    self._log_file = open(log_path, "w")
                    self.log.info(f"transferring {file_path} from {local_directory} to {external_directory}")
                    # generate rsync command with args
                    if sys.platform == "win32":
                        # if windows, rsync expects absolute paths with driver letters to use
                        # /cygdrive/drive-letter and / not \
                        # example: /cygdrive/c/test/filename.extension
                        file_path = file_path.replace("\\", "/").replace(":", "")
                        file_path = "/cygdrive/" + file_path
                        external_dir = external_dir.replace("\\", "/").replace(":", "")
                        external_dir = "/cygdrive/" + external_dir + "/" + filename
                        cmd_with_args = self._flatten([self._protocol, self._flags, file_path, external_dir])
                    elif sys.platform == "darwin" or "linux" or "linux2":
                        # linux or darwin, paths defined as below
                        cmd_with_args = self._flatten(
                            [
                                self._protocol,
                                self._flags,
                                file_path,
                                Path(external_dir, filename),
                            ]
                        )
                    subprocess = Popen(cmd_with_args, stdout=self._log_file)
                    self._log_file.close()
                    time.sleep(1.0)
                    # lets monitor the progress of the individual file if size > 1 GB
                    if file_size_mb > 1024:
                        self.log.info(f"{filename} is > 1 GB")
                        # wait for subprocess to start otherwise log file won't exist yet
                        time.sleep(10.0)
                        file_progress = 0
                        previous_progress = 0
                        stuck_time_s = 0
                        while file_progress < 100:
                            start_time_s = time.time()
                            # open the stdout file in a temporary handle with r+ mode
                            f = open(log_path, "r+")
                            # read the last line
                            line = f.readlines()[-1]
                            # try to find if there is a % in the last line
                            try:
                                # grab the index of the % symbol
                                index = line.find("%")
                                # a location with % has been found
                                if index != -1:
                                    # grab the string of the % progress
                                    value = line[index - 4 : index]
                                    # strip and convert to float
                                    file_progress = float(value.rstrip())
                                # we must be at the last line of the file
                                else:
                                    # go back to beginning of file
                                    f.seek(0)
                                    # read line that must be 100% line
                                    line = f.readlines()[-4]
                                    # grab the index of the % symbol
                                    index = line.find("%")
                                    # grab the string of the % progress
                                    value = line[index - 4 : index]
                                    # strip and convert to float
                                    file_progress = float(value.rstrip())
                            # no lines in the file yet
                            except Exception:
                                file_progress = 0
                            # sum to transferred amount to track progress
                            self.progress = (
                                (total_transferred_mb + file_size_mb * file_progress / 100) / total_size_mb * 100
                            )
                            end_time_s = time.time()
                            # keep track of how long stuck at same progress
                            if self.progress == previous_progress:
                                stuck_time_s += end_time_s - start_time_s
                                # break if exceeds timeout
                                if stuck_time_s > +self._timeout_s:
                                    break
                            previous_progress = self.progress
                            self.log.info(
                                self.log.info(f"{self.filename} transfer is {self.progress:.2f} [%] complete.")
                            )
                            # close temporary stdout file handle
                            f.close()
                            # pause for 10 sec
                            time.sleep(10.0)
                    else:
                        subprocess.wait()
                        self.progress = (total_transferred_mb + file_size_mb) / total_size_mb * 100
                        self.log.info(self.log.info(f"{self.filename} transfer is {self.progress:.2f} [%] complete."))
                    self.log.info(f"{filename} transfer complete")
                    # wait for process to finish before cleaning log file
                    time.sleep(10.0)
                    # clean up and remove the temporary log file
                    os.remove(log_path)
                    # update the total transfered amount
                    total_transferred_mb += file_size_mb
                # clean up the local subdirs and files
                for file in delete_list:
                    # f is a relative path, convert to absolute
                    local_file_path = os.path.join(local_directory.absolute(), file)
                    external_file_path = os.path.join(external_directory.absolute(), file)
                    # .zarr is directory but os.path.isdir will return False
                    if os.path.isdir(local_file_path) or ".zarr" in local_dir:
                        # TODO how to hash check zarr -> directory instead of file?
                        shutil.rmtree(local_file_path)
                    elif os.path.isfile(local_file_path):
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
                            except external_file_path.DoesNotExist:
                                self.log.warning(f"no external file exists at {external_file_path}")
                        else:
                            # remove local file
                            self.log.info(f"deleting {local_file_path}")
                            os.remove(local_file_path)
                    else:
                        self.log.warning(f"{local_file_path} is not a file or directory.")
                end_time = time.time()
                total_time = end_time - start_time
                self.log.info(f"{self.filename} transfer complete, total time: {total_time:.2f} [s]")
                subprocess.kill()
                retry_num += 1

    def _flatten(self, lst: List[Any]) -> Iterable[Any]:
        """Flatten a list using generators comprehensions.
        Returns a flattened version of list lst.
        """
        for sublist in lst:
            if isinstance(sublist, list):
                for item in sublist:
                    yield item
            else:
                yield sublist
