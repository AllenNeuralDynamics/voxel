import os
import shutil
import time
from pathlib import Path
from subprocess import DEVNULL, Popen

from .base import VoxelFileTransfer


class RobocopyFileTransfer(VoxelFileTransfer):
    r"""Voxel driver for Robocopy file transfer process.

    Process will transfer files with the following regex
    format:

    From -> \\\\local_path\\\\acquisition_name\\\\filename*
    To -> \\\\external_path\\\\acquisition_name\\\\filename*

    :param external_path: External path of files to be transferred
    :param local_path: Local path of files to be transferred
    :type external_path: str
    :type local_path: str
    """

    def __init__(self, external_path: str, local_path: str, name: str = 'robocopy'):
        super().__init__(external_path, local_path, name)
        self._protocol = 'robocopy'

    def _run(self) -> None:  # noqa: C901, PLR0912, PLR0915
        start_time = time.time()
        local_directory = Path(self._local_path, self._acquisition_name)
        external_directory = Path(self._external_path, self._acquisition_name)
        log_path = Path(local_directory, '%s.log' % self._filename)
        transfer_complete = False
        retry_num = 0
        subprocess: Popen | None = None
        # loop over number of attempts in the event that a file transfer fails
        while transfer_complete is False and retry_num <= self._max_retry - 1:
            # generate a list of subdirs and files in the parent local dir to delete at the end
            delete_list = [p.name for p in local_directory.iterdir() if self.filename in p.name]

            # generate a list of files to copy
            file_list = {}
            for p in local_directory.glob('**/*'):
                if p.is_file() and self.filename in p.name and p.name != log_path.name:
                    file_list[str(p)] = p.stat().st_size / 1024**2
            total_size_mb = sum(file_list.values())
            # sort the file list based on the file sizes and create a list for transfers
            sorted_file_list = dict(sorted(file_list.items(), key=lambda item: item[1]))
            total_transferred_mb = 0
            # if file list is empty, transfer must be complete
            if not sorted_file_list:
                transfer_complete = True
            # if not, try to initiate transfer again
            else:
                num_files = len(sorted_file_list)
                self.log.info('attempt %s/%s, tranferring %s files.', retry_num + 1, self._max_retry, num_files)
                for file_path, file_size_mb in sorted_file_list.items():
                    # transfer just one file and iterate
                    # split filename and path
                    [local_dir, filename] = os.path.split(file_path)
                    self.log.info('transfering %s', filename)
                    # specify external directory
                    # need to change directories to str because they are Path objects
                    external_dir = local_dir.replace(str(local_directory), str(external_directory))
                    # robocopy flags
                    # /j unbuffered copy for transfer speed stability
                    # /mov deletes local files after transfer
                    # /if move only the specified filename
                    # /njh no job header in log file
                    # /njs no job summary in log file
                    cmd_with_args = '%s %s %s /j /if %s /njh /njs /log:%s' % (
                        self._protocol,
                        local_dir,
                        external_dir,
                        filename,
                        log_path,
                    )
                    # stdout to PIPE will cause malloc errors on exist
                    # no stdout will print subprocess to python
                    # stdout to DEVNULL will supresss subprocess output
                    subprocess = Popen(cmd_with_args, stdout=DEVNULL)
                    # wait one second for process to start before monitoring log file for progress
                    time.sleep(1.0)
                    # lets monitor the progress of the individual file if size > 1 GB
                    max_mbs = 1024
                    max_percent = 100
                    if file_size_mb > max_mbs:
                        self.log.info('%s is > 1 GB', filename)
                        # wait for subprocess to start otherwise log file won't exist yet
                        time.sleep(1.0)
                        file_progress = 0
                        previous_progress = 0
                        stuck_time_s = 0
                        while file_progress < max_percent:
                            start_time_s = time.time()

                            with log_path.open() as f:
                                line = f.readlines()[-1]  # read the last line

                            # try to find if there is a % in the last line
                            try:
                                # convert the string to a float
                                file_progress = float(line.replace('%', ''))
                            # line did not contain %
                            except ValueError:
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
                                if stuck_time_s >= self._timeout_s:
                                    self.log.info('timeout exceeded, restarting file transfer.')
                                    break
                            else:
                                stuck_time_s = 0
                            previous_progress = self.progress
                            self.log.info('file transfer is %.2f %% complete.', self.progress)
                            # pause for 10 sec
                            time.sleep(10.0)
                    else:
                        subprocess.wait()
                        self.progress = (total_transferred_mb + file_size_mb) / total_size_mb * 100
                        self.log.info('file transfer is %.2f %% complete.', self.progress)
                    self.log.info('%s transfer complete', filename)
                    # wait for process to finish before cleaning log file
                    time.sleep(10.0)
                    # clean up and remove the temporary log file
                    log_path.unlink()
                    # update the total transfered amount
                    total_transferred_mb += file_size_mb
                # clean up the local subdirs and files
                for file in delete_list:
                    # f is a relative path, convert to absolute
                    local_file_path = local_directory / file
                    external_file_path = external_directory / file
                    # .zarr is directory but os.path.isdir will return False
                    if local_file_path.is_dir() or '.zarr' in local_file_path.name:
                        # TODO how to hash check zarr -> directory instead of file?
                        shutil.rmtree(local_file_path)
                    elif local_file_path.is_file():
                        # verify transfer with hashlib
                        if self._verify_transfer:
                            # put in try except in case no external file found
                            try:
                                # if hash is verified delete file
                                if self._verify_file(str(local_file_path), str(external_file_path)):
                                    # remove local file
                                    self.log.info('deleting %s', local_file_path)
                                    local_file_path.unlink()
                                # if has fails, external file is corrupt
                                else:
                                    # remove external file, try again
                                    self.log.info('hashes did not match, deleting %s', external_file_path)
                                    external_file_path.unlink()
                            except FileNotFoundError:
                                self.log.warning('no external file exists at %s', external_file_path)
                        else:
                            # remove local file
                            self.log.info('deleting %s', local_file_path)
                            local_file_path.unlink()
                    else:
                        msg = '%s is not a file or directory.' % local_file_path
                        raise ValueError(msg)
                end_time = time.time()
                total_time = end_time - start_time
                self.log.info('transfer complete, total time: %s sec', total_time)
                subprocess.kill() if subprocess else None
                retry_num += 1
