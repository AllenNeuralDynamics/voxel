import socket

from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
import uvicorn

from voxel.utils.log_config import LogColor, get_logger

logger = get_logger("voxel.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Laser Control API", version="0.1", lifespan=lifespan)


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # The address doesn't need to be reachable; it's used to determine the local IP.
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


class Settings:
    host: str = "0.0.0.0"
    port: int = 80
    ip: str = get_local_ip()


settings = Settings()

url_msg = f"Application will be available at: {LogColor.BLUE}http://{settings.ip}:{settings.port}{LogColor.RESET}"


def run():
    try:
        logger.info(url_msg)
        uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    except KeyboardInterrupt:
        print("Shutdown requested. Exiting...")


if __name__ == "__main__":
    run()
