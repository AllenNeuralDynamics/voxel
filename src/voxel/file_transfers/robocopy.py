import os
import shutil
import time
from pathlib import Path
from voxel.descriptors.deliminated_property import DeliminatedProperty
from subprocess import DEVNULL, Popen

from voxel.file_transfers.base import BaseFileTransfer


class RobocopyFileTransfer(BaseFileTransfer):
    """
    Voxel driver for Robocopy file transfer process.

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
        self._protocol = "robocopy"

    def _run(self):
        start_time = time.time()
        local_directory = Path(self._local_path, self._acquisition_name)
        external_directory = Path(self._external_path, self._acquisition_name)
        log_path = Path(local_directory, f"{self._filename}.log")
        transfer_complete = False
        retry_num = 0
        # loop over number of attempts in the event that a file transfer fails
        while transfer_complete == False and retry_num <= self._max_retry-1:
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
                    # check and only add if filename matches tranfer's filename but not the log file
                    if self.filename in name and name != log_path:
                        file_list[os.path.join(path, name)] = os.path.getsize(os.path.join(path, name))/1024**2
            total_size_mb = sum(file_list.values())
            # sort the file list based on the file sizes and create a list for transfers
            sorted_file_list = dict(sorted(file_list.items(), key = lambda item: item[1]))
            total_transferred_mb = 0
            # if file list is empty, transfer must be complete
            if not sorted_file_list:
                transfer_complete = True
            # if not, try to initiate transfer again
            else:
                num_files = len(sorted_file_list)
                self.log.info(f'attempt {retry_num+1}/{self._max_retry}, tranferring {num_files} files.')
                for file_path, file_size_mb in sorted_file_list.items():
                    # transfer just one file and iterate
                    # split filename and path
                    [local_dir, filename] = os.path.split(file_path)
                    self.log.info(f'transfering {filename}')
                    # specify external directory
                    # need to change directories to str because they are Path objects
                    external_dir = local_dir.replace(str(local_directory), str(external_directory))
                    # robocopy flags
                    # /j unbuffered copy for transfer speed stability
                    # /mov deletes local files after transfer
                    # /if move only the specified filename
                    # /njh no job header in log file
                    # /njs no job summary in log file
                    cmd_with_args = f'{self._protocol} {local_dir} {external_dir} \
                        /j /if {filename} /njh /njs /log:{log_path}'
                    # stdout to PIPE will cause malloc errors on exist
                    # no stdout will print subprocess to python
                    # stdout to DEVNULL will supresss subprocess output
                    subprocess = Popen(cmd_with_args, stdout=DEVNULL)
                    # wait one second for process to start before monitoring log file for progress
                    time.sleep(1.0)
                    # lets monitor the progress of the individual file if size > 1 GB
                    if file_size_mb > 1024:
                        self.log.info(f'{filename} is > 1 GB')
                        # wait for subprocess to start otherwise log file won't exist yet
                        time.sleep(1.0)
                        file_progress = 0
                        previous_progress = 0
                        stuck_time_s = 0
                        while file_progress < 100:
                            start_time_s = time.time()
                            # open log file
                            f = open(log_path, 'r')
                            # read the last line
                            line = f.readlines()[-1]
                            # close the log file
                            f.close()
                            # try to find if there is a % in the last line
                            try:
                                # convert the string to a float
                                file_progress = float(line.replace('%',''))
                            # line did not contain %
                            except:
                                file_progress = 0
                            # sum to transferred amount to track progress
                            self._progress = (total_transferred_mb +
                                            file_size_mb * file_progress / 100) / total_size_mb * 100
                            end_time_s = time.time()
                            # keep track of how long stuck at same progress
                            if self.progress == previous_progress:
                                stuck_time_s += (end_time_s - start_time_s)
                                # break if exceeds timeout
                                if stuck_time_s >= self._timeout_s:
                                    self.log.info('timeout exceeded, restarting file transfer.')
                                    break
                            else:
                                stuck_time_s  = 0
                            previous_progress = self.progress
                            self.log.info(f'{self.filename} transfer is {self.progress:.2f} [%] complete.')
                            # pause for 10 sec
                            time.sleep(10.0)
                    else:
                        subprocess.wait()
                        self._progress = (total_transferred_mb + file_size_mb) / total_size_mb * 100
                        self.log.info(f'{self.filename} transfer is {self.progress:.2f} [%] complete.')
                    self.log.info(f'{filename} transfer complete')
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
                                    self.log.info(f'deleting {local_file_path}')
                                    os.remove(local_file_path)
                                # if has fails, external file is corrupt
                                else:
                                    # remove external file, try again
                                    self.log.info(f'hashes did not match, deleting {external_file_path}')
                                    os.remove(external_file_path)
                                    pass
                            except:
                                self.log.warning(f'no external file exists at {external_file_path}')
                        else:
                            # remove local file
                            self.log.info(f'deleting {local_file_path}')
                            os.remove(local_file_path)
                    else:
                        raise ValueError(f'{local_file_path} is not a file or directory.')
                    # TODO REMOVE
                    os.remove(external_file_path)
                end_time = time.time()
                total_time = end_time - start_time
                self.log.info(f'{self.filename} transfer complete, total time: {total_time:.2f} [s]')
                subprocess.kill()
                retry_num += 1