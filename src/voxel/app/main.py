# from pathlib import Path

# import uvicorn
# from fastapi import APIRouter, FastAPI, Request, WebSocket
# from fastapi.concurrency import asynccontextmanager, run_in_threadpool
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import JSONResponse
# from fastapi.staticfiles import StaticFiles
# from pydantic import ValidationError

# from voxel.app.messaging import MessageBus, MessageEnvelope, SignalStream, StreamIntervals, WebSocketConnection
# from voxel.devices.base import VoxelDeviceModel
# from voxel.instrument import ConfigLoadError, InstrumentConfig, Instrument
# from voxel.utils.common import get_local_ip
# from voxel.utils.log_config import get_logger

# logger = get_logger("app")

# HOST = get_local_ip()
# PORT = 5432
# BASE_URL = f"http://{HOST}:{PORT}"


# class InstrumentService:
#     log = get_logger("app.instrument")

#     config_file_name = "config.yaml"

#     STAGE_INTERVALS = StreamIntervals(0.15, 0.0333)

#     def __init__(self, directory: Path, bus: MessageBus):
#         self.config_path = directory / self.config_file_name

#         self.bus = bus

#         self.instrument = Instrument((InstrumentConfig.from_yaml(self.config_path)))

#         self.streams: list[SignalStream] = []
#         self.streams.append(
#             SignalStream(
#                 intervals=self.STAGE_INTERVALS,
#                 getter=lambda: run_in_threadpool(lambda: self.instrument.stage.position_mm.dict()),
#                 publisher=self.bus,
#                 topic="stage",
#             )
#         )

#     def reload(self) -> Instrument:
#         self.instrument.close() if self.instrument else None
#         self.stop_streams()
#         self.instrument = Instrument((InstrumentConfig.from_yaml(self.config_path)))
#         self.start_streams()
#         return self.instrument

#     def start_streams(self):
#         [stream.start() for stream in self.streams]

#     def stop_streams(self):
#         [stream.stop() for stream in self.streams]

#     async def shutdown(self):
#         self.stop_streams()
#         await self.bus.shutdown()
#         self.instrument.close()

#     # async def _get_stage_position(self) -> dict[str, float]:
#     #     return self.instrument.stage.position_mm.dict()


# mgr = InstrumentService(directory=Path(__file__).parent / "example", bus=MessageBus())

# api = APIRouter(prefix="/api")


# @api.get("/config")
# async def get_config() -> InstrumentConfig:
#     return mgr.instrument.config


# @api.put("/reload_config")
# async def reload_config() -> InstrumentConfig:
#     mgr.reload()
#     return mgr.instrument.config


# @api.get("/instrument")
# async def get_instrument_info() -> dict[str, dict[str, str]]:
#     return {
#         "channels": {name: f"{BASE_URL}/api/channel/{name}" for name in mgr.instrument.channels},
#         "devices": {name: f"{BASE_URL}/api/device/{name}" for name in mgr.instrument.devices},
#     }


# @api.get("/device/{device_name}")
# async def get_device_info(device_name: str) -> VoxelDeviceModel:
#     device = mgr.instrument.devices.get(device_name)
#     if device is not None:
#         return await run_in_threadpool(lambda: device.snapshot)
#     raise ValueError(f"Device '{device_name}' not found.")


# @api.get("/channel/{channel_name}")
# async def get_channel_info(channel_name: str) -> dict[str, VoxelDeviceModel]:
#     channel = mgr.instrument.channels.get(channel_name)
#     if channel is None:
#         raise ValueError(f"Channel '{channel_name}' not found.")
#     return await run_in_threadpool(lambda: channel.snapshot)


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     mgr.start_streams()
#     yield
#     await mgr.shutdown()


# app = FastAPI(title="Spim Studio", version="0.1", lifespan=lifespan)

# app.add_middleware(middleware_class=CORSMiddleware, allow_origins=["http://localhost:5173"], allow_headers=["*"])

# app.include_router(api)


# @app.websocket("/ws")
# async def websocket_endpoint(websocket: WebSocket):
#     await websocket.accept()
#     client = await mgr.bus.connect(WebSocketConnection(websocket))
#     publisher = mgr.bus
#     try:
#         while True:
#             # Expect subscription messages, e.g., {"subscribe": ["device123", "device456"], "unsubscribe": ["device789"]}
#             # or {"publish": {"topic": "device123", "payload": Any, "timestamp": 1234567890}}
#             msg = await websocket.receive_json()
#             if "subscribe" in msg:
#                 try:
#                     await client.subscribe(set(msg["subscribe"]))
#                 except KeyError:
#                     logger.error("Invalid subscription message format.")
#                     continue
#             if "unsubscribe" in msg:
#                 try:
#                     await client.unsubscribe(set(msg["unsubscribe"]))
#                 except KeyError:
#                     logger.error("Invalid unsubscription message format.")
#                     continue
#             if "publish" in msg:
#                 try:
#                     envelope = MessageEnvelope(**msg["publish"])
#                     await publisher.broadcast(envelope.topic, envelope)
#                     logger.info(f"Client published message: {envelope}")
#                 except ValidationError as e:
#                     logger.error(f"Invalid message format: {e}")
#                     continue
#     except Exception as e:
#         logger.error(f"Websocket error: {e}")
#         await mgr.bus.disconnect(client)


# app.mount("/", StaticFiles(directory=Path(__file__).parent / "frontend" / "build", html=True), name="app")


# @app.exception_handler(ValidationError)
# async def validation_error_handler(request: Request, exc: ValidationError):
#     formatted_errors = []
#     for error in exc.errors():
#         if (ctx := error.get("ctx")) and (err_inst := ctx.get("error")) and isinstance(err_inst, ConfigLoadError):
#             print(f"Ctxxt: {error.get('ctx', {})}")
#             formatted_errors.append({"field": error.get("loc", []), "messages": str(err_inst).split("; ")})
#     if formatted_errors:
#         return JSONResponse(
#             status_code=422,
#             content={
#                 "message": "Validation error in configuration parameters.",
#                 "errors": formatted_errors,
#             },
#         )
#     raise exc


# def run():
#     try:
#         uvicorn.run(app, host=get_local_ip(), port=5432, log_level="info")
#     except KeyboardInterrupt:
#         print("Shutdown requested. Exiting...")


# if __name__ == "__main__":
#     from voxel.utils.log_config import setup_logging

#     setup_logging()
#     run()
