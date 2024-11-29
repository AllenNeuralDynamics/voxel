import threading
from abc import abstractmethod
from pathlib import Path

from imohash import hashfile

from voxel.utils.log_config import get_component_logger


class VoxelFileTransfer:
    """
    Base class for all voxel file transfer processes.

    Process will transfer files with the following regex
    format:

    From -> \\\\local_path\\\\acquisition_name\\\\filename*
    To -> \\\\external_path\\\\acquisition_name\\\\filename*

    :param external_path: External path of files to be transferred
    :param local_path: Local path of files to be transferred
    :type external_path: str
    :type local_path: str
    :raise ValueError: Same external and local path
    """

    def __init__(self, external_path: str, local_path: str, name: str = "voxel_file_transfer") -> None:
        self.name = name
        self.log = get_component_logger(self)
        self._external_path = Path(external_path)
        self._local_path = Path(local_path)
        if self._external_path == self._local_path:
            raise ValueError("External path and local path cannot be the same")
        self._filename = None
        self._max_retry = 0
        self._acquisition_name = Path()
        self._verify_transfer = False
        self._num_tries = 1
        self._timeout_s = 60
        self.progress = 0

    @property
    @abstractmethod
    def filename(self) -> str:
        """
        The base filename of files to be transferred.

        :return: The base filename
        :rtype: str
        """

        return self._filename

    @filename.setter
    @abstractmethod
    def filename(self, filename: str) -> None:
        """
        The base filename of files to be transferred.\n

        :param filename: The base filename
        :type filename: str
        """

        self.log.info(f"setting filename to: {filename}")
        self._filename = filename

    @property
    @abstractmethod
    def acquisition_name(self) -> str:
        """
        The base acquisition name of files to be transferred.

        :return: The base filename
        :rtype: str
        """

        return self._acquisition_name

    @acquisition_name.setter
    @abstractmethod
    def acquisition_name(self, acquisition_name: str) -> None:
        """
        The base acquisition name of files to be transferred.

        :param acquisition_name: The base acquisition_name
        :type acquisition_name: str
        """

        self._acquisition_name = Path(acquisition_name)
        self.log.info(f"setting acquisition name to: {acquisition_name}")

    @property
    @abstractmethod
    def local_path(self) -> str:
        """
        The local path of files to be transferred.

        :return: The local path
        :rtype: str
        """

        return self._local_path

    @local_path.setter
    @abstractmethod
    def local_path(self, local_path: str) -> None:
        """
        The local path of files to be transferred.

        :param local_path: The local path
        :type local_path: str
        """

        self._local_path = Path(local_path)
        self.log.info(f"setting local path to: {local_path}")

    @property
    @abstractmethod
    def external_path(self) -> str:
        """
        The external path of files to be transferred.

        :return: The external path
        :rtype: str
        """

        return self._external_path

    @external_path.setter
    @abstractmethod
    def external_path(self, external_path: str) -> None:
        """
        The external path of files to be transferred.

        :param external_path: The external path
        :type external_path: str
        """

        self._external_path = Path(external_path)
        self.log.info(f"setting local path to: {external_path}")

    @property
    @abstractmethod
    def verify_transfer(self) -> str:
        """
        State of transfer process.

        :return: The transfer process state
        :rtype: str
        """

        return self._verify_transfer

    @verify_transfer.setter
    @abstractmethod
    def verify_transfer(self, verify_transfer: bool) -> None:
        """
        State of transfer process.

        :param verify_transfer: The transfer process state
        :type verify_transfer: bool
        """

        self._verify_transfer = verify_transfer
        self.log.info(f"setting verify transfer to: {verify_transfer}")

    @property
    @abstractmethod
    def max_retry(self) -> int:
        """
        Number of times to retry the transfer process.

        :return: Number of retry attempts
        :rtype: int
        """

        return self._max_retry

    @max_retry.setter
    @abstractmethod
    def max_retry(self, max_retry: int) -> None:
        """
        Number of times to retry the transfer process.

        :param max_retry: Number of retry attempts
        :type max_retry: int
        """

        self._max_retry = max_retry
        self.log.info(f"setting max retry to: {max_retry}")

    @property
    @abstractmethod
    def timeout_s(self) -> float:
        """
        Timeout for the transfer process.

        :return: Timeout in seconds
        :rtype: float
        """

        return self._timeout_s

    @timeout_s.setter
    @abstractmethod
    def timeout_s(self, timeout_s: float) -> None:
        """
        Timeout for the transfer process.

        :param timeout_s: Timeout in seconds
        :type timeout_s: float
        """

        self._timeout_s = timeout_s
        self.log.info(f"setting timeout to: {timeout_s}")

    @property
    @abstractmethod
    def signal_process_percent(self) -> float:
        """
        Get the progress of the transfer process.

        :return: Progress in percent
        :rtype: float
        """

        state = {}
        state["Transfer Progress [%]"] = self.progress
        self.log.info(f"{self._filename} transfer progress: {self.progress:.2f} [%]")
        return state

    @abstractmethod
    def start(self):
        """
        Start the transfer process.
        """

        self.log.info(f"transferring from {self._local_path} to {self._external_path}")
        self.thread = threading.Thread(target=self._run)
        self.thread.start()

    @abstractmethod
    def wait_until_finished(self):
        """
        Wait for the transfer process to finish.
        """

        self.thread.join()

    @abstractmethod
    def is_alive(self) -> bool:
        """
        Check if the transfer process is still running.

        :return: State of thread
        :rtype: bool
        """

        return self.thread.is_alive()

    @abstractmethod
    def _verify_file(self, local_file_path: str, external_file_path: str) -> bool:
        """
        Internal function that hash checks a transfered file.

        :param local_file_path: Local path of files
        :type local_file_path: str
        :param external_file_path: External path of files
        :type external_file_path: str
        :return: State of transfered file
        :rtype: bool
        """
        # verifying large files with a full checksum is too time consuming
        # verifying based on file size alone is not thorough
        # use imohash library to perform hasing on small subset of file
        # imohash defaults to reading 16K bits (i.e. 1<<14) from beginning, middle, and end
        local_hash = hashfile(local_file_path, sample_size=1 << 14)
        external_hash = hashfile(external_file_path, sample_size=1 << 14)
        if local_hash == external_hash:
            self.log.info(f"{local_file_path} and {external_file_path} hashes match")
            return True
        else:
            self.log.info(f"hash mismatch for {local_file_path} and {external_file_path}")
            self.log.info(f"{local_file_path} hash = {local_hash}")
            self.log.info(f"{external_file_path} hash = {external_hash}")
            return False

    @abstractmethod
    def _run(self):
        """
        Internal function that runs the transfer process.
        """
        pass
