from fastapi import FastAPI
from main import CONFIG_PATH
from pydantic_settings import BaseSettings

from voxel.builder import VoxelBuilder, VoxelSpecs
from fastapi.middleware.cors import CORSMiddleware

from voxel.server.instrument_router import InstrumentRouter

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:4173",
]


class Settings(BaseSettings):
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # API settings
    api_prefix: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


def run_server(app: FastAPI) -> None:
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port, reload=settings.debug)


def main() -> None:
    config = VoxelSpecs.from_yaml(file_path=CONFIG_PATH)
    builder = VoxelBuilder(config=config)
    with builder.build_instrument() as instrument:
        for camera in instrument.cameras.values():
            camera.reset_roi()

        app = FastAPI()

        app.add_middleware(
            middleware_class=CORSMiddleware,
            allow_origins=ALLOWED_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/")
        async def root() -> dict[str, str]:
            return {"message": "Welcome to the Voxel Device API"}

        app.include_router(InstrumentRouter(instrument))

        # @app.on_event("shutdown")

        run_server(app)


if __name__ == "__main__":
    from voxel.utils.log_config import setup_logging

    setup_logging(level="INFO", detailed=True)
    main()
