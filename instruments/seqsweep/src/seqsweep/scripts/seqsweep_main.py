import argparse
import logging
import logging.config
import os
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from ficus.database.filesys import FileSysStore  # type: ignore
from ficus.services.configs import get_config  # type: ignore
from one_liner.server import RouterServer  # type: ignore

from seqsweep.seqsweep import SeqSweep
from seqsweep.seqsweep_config_model import SeqSweepSystemConfig


class ZMQServer(RouterServer):
    def __init__(
        self,
        rpc_port: str = "5555",
        broadcast_port: str = "5556",
        config: dict | None = None,
        instances: dict | None = None,
    ):
        super().__init__(
            rpc_port=rpc_port,
            broadcast_port=broadcast_port,
            instances=instances,
            config=config,
        )

        self.log = logging.getLogger(self.__class__.__name__)
        self.config = config or {}

        if instances is None:
            raise ValueError("instances dictionary must be provided to ZMQServer")

        if "seqsweep" in instances:
            self.seqsweep: SeqSweep = instances["seqsweep"]


def main():
    parser = argparse.ArgumentParser(prog="seqsweep")
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override the console log level specified in the config file.",
    )
    parser.add_argument(
        "--config-dir",
        type=str,
        default=None,
        help="Absolute or relative path to the configs directory.",
    )
    parser.add_argument(
        "--hostname",
        default="dev_computer",
        help="Hostname scope for config overrides (configs/hostname/<hostname>/...).",
    )

    args = parser.parse_args()
    logger = logging.getLogger()

    # Config
    if args.config_dir:
        config_dir = Path(args.config_dir).resolve()
    else:
        config_dir = Path(__file__).resolve().parents[3] / "configs"
    data_store = FileSysStore(rootdir=config_dir, scopes={"defaults", "hostname"})
    current_scopes = {"hostname": args.hostname}
    logging_config = get_config(data_store=data_store, namespace="logging")
    seqsweep_config = get_config(data_store=data_store, namespace="seqsweep", scope_identifiers=current_scopes)
    seqsweep_config.data["logging"] = logging_config.data.get("logging", {})
    config = SeqSweepSystemConfig(**seqsweep_config.data)

    # Set log level and get Logger
    if args.log_level and config.logging.handlers and "console" in config.logging.handlers:
        config.logging.handlers["console"].level = args.log_level
    logging.config.dictConfig(config.logging.model_dump(by_alias=True, exclude_none=True))

    old_factory = logging.getLogRecordFactory()
    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.project = "seqSweep"
        record.version = version("seqsweep")
        record.comp_id = os.getenv("aibs_comp_id", "unknown")
        record.msg = f"SeqSweep: {record.msg}"
        return record

    logging.setLogRecordFactory(record_factory)

    # Open the scanner (rig) before serving it
    seqsweep = SeqSweep(config)
    seqsweep.open()

    server = ZMQServer(
        instances={"seqsweep": seqsweep},
        config=config.router_server_api.model_dump(),
        **config.router_server_kwargs.model_dump(),
    )

    logger.info("SeqSweep ZMQ Server started!")
    server.run()

    try:
        while not server.context.closed:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down seqsweep server..")
    finally:
        seqsweep.close()


if __name__ == "__main__":
    main()
