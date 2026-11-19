"""A real run: a simulated SPIM microscope behind a real HTTP server, driven only over HTTP.

Run: ``uv run python -m prototypes.interface.demo``"""

import asyncio
import http.client
import json
import tempfile
from pathlib import Path
from typing import Any

import uvicorn
from vxl_records import SQLiteRecords

from tests.instruments.spim.support import config_data, simulated, template
from vxl.instruments.spim.instrument import Microscope
from vxl.instruments.spim.task import Task
from vxl.station.instrument.folder import InstrumentFolder
from vxl.system import System

from .web import build_app

PORT = 8771
seen: dict[str, str | None] = {"etag": None}
"""The ETag of the last answer."""
REGION = {"outline": {"kind": "explicit_points", "points": [{"x": 0, "y": 0}]}, "bounds": [0, 1]}


def _call(
    method: str, path: str, body: object | None = None, headers: dict[str, str] | None = None
) -> tuple[int, dict[str, str], Any]:
    connection = http.client.HTTPConnection("127.0.0.1", PORT)
    data = None if body is None else json.dumps(body)
    connection.request(method, path, body=data, headers={"Content-Type": "application/json", **(headers or {})})
    answer = connection.getresponse()
    raw = answer.read()
    connection.close()
    headers = {name.lower(): value for name, value in answer.getheaders()}
    try:
        return answer.status, headers, json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return answer.status, headers, raw.decode(errors="replace")[:200]


def _raw(method: str, path: str, text: str) -> tuple[int, dict[str, str], Any]:
    connection = http.client.HTTPConnection("127.0.0.1", PORT)
    connection.request(method, path, body=text, headers={"Content-Type": "application/json"})
    answer = connection.getresponse()
    raw = answer.read()
    connection.close()
    return answer.status, {}, raw.decode()


async def call(
    method: str, path: str, body: object | None = None, headers: dict[str, str] | None = None
) -> tuple[int, Any]:
    status, received, answer = await asyncio.to_thread(_call, method, path, body, headers)
    seen["etag"] = received.get("etag")
    sent = f" [{', '.join(f'{k}: {v}' for k, v in headers.items())}]" if headers else ""
    location = f"  Location: {received['location']}" if "location" in received else ""
    method = method + sent
    shown = json.dumps(answer)[:110] if answer is not None else ""
    print(f"{method:6} {path:44} -> {status}{location}  {shown}")
    return status, answer


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        folder = InstrumentFolder.create(template(simulated(config_data())), "left", home)
        records = SQLiteRecords(home / "records.sqlite3", resolve_root=lambda spec: home / spec.path.as_posix())
        system = System(store=home / "data", scratch=home / "scratch", remotes={}, max_ram_fraction=0.1)
        microscope = Microscope(folder, records=records, system=system)
        await microscope.open()
        server = uvicorn.Server(uvicorn.Config(build_app(microscope), port=PORT, log_level="warning"))
        serving = asyncio.create_task(server.serve())
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.05)
        try:
            await run(microscope.view.value.state.task)
        finally:
            server.should_exit = True
            await serving
            await microscope.close()


async def run(defaults: Any) -> None:
    def task(task_id: str) -> dict[str, Any]:
        return Task.complete({"id": task_id, "region": REGION, "profiles": ["gfp"]}, defaults).model_dump(mode="json")

    print("== interface and docs")
    _, described = await call("GET", "/interface")
    print(f"   operations: {sorted(described['operations'])}")
    print(f"   view schema fields: {sorted(described['view']['properties'])}")
    _, document = await call("GET", "/openapi.json")
    print(f"   openapi paths: {len(document['paths'])}, schemas: {len(document['components']['schemas'])}")
    edit = document["paths"]["/state/plan/{task_id}"]["patch"]
    print(f"   PATCH /state/plan/{{task_id}} parameters: {[p['name'] for p in edit['parameters']]}")
    print(f"   its responses: {sorted(edit['responses'])}")

    print("== tasks")
    await call("POST", "/state/plan", {"task": task("a")})
    await call("POST", "/state/plan", {"task": task("b")})
    await call("PATCH", "/state/plan/a", {"profiles": ["gfp"]})
    await call("POST", "/state/plan:reorder", {"task_ids": ["b", "a"]})
    _, plan = await call("GET", "/state/plan")
    print(f"   order now: {[t['id'] for t in plan]}")
    await call("POST", "/state/plan:remove", {"task_ids": ["b"]})
    await call("GET", "/state/plan/b")

    print("== profile, writer, history")
    await call("PATCH", "/state/profiles/gfp", {"spacing": 2.5, "label": "GFP"})
    await call("PATCH", "/state/writer", {"shard_z_chunks": 4})
    await call("POST", "/history:undo")
    await call("POST", "/history:undo")
    _, profile = await call("GET", "/state/profiles/gfp")
    print(f"   2 undos (writer, then the 1 profile edit): spacing {profile['spacing']}, label {profile['label']}")

    print("== devices, through the instrument")
    await call("PATCH", "/devices/camera", {"exposure_time_ms": 25.0})
    await call("GET", "/devices/camera")

    print("== refusals")
    await call("PATCH", "/state/plan/a", {"colour": "red"})
    await call("PATCH", "/state/plan/zzz", {"profiles": ["gfp"]})
    await call("PATCH", "/state/profiles/gfp", {"spacing": -1})
    await call("POST", "/state/plan", {"task": {"id": "c"}})
    await call("POST", "/preview:stop")
    await call("POST", "/state/plan:remove", {"task_ids": ["zzz"]})
    await call("PATCH", "/state/profiles/nope", {"label": "x"})
    await call("GET", "/state/writer/x")
    await call("PATCH", "/devices/nope", {"x": 1})
    await call("PATCH", "/devices/camera", {"nope": 1})
    await call("POST", "/devices/camera:nope")
    print("== versions (ETag, If-Match, If-None-Match)")
    await call("GET", "/state/plan/a")
    old = seen["etag"]
    await call("GET", "/state/plan/a", headers={"If-None-Match": str(old)})
    await call("POST", "/state/plan", {"task": task("c")})
    print("   (an edit to task c leaves task a's tag valid:)")
    await call("PATCH", "/state/plan/a", {"overlap": {"x": "20 %", "y": "10 %"}}, headers={"If-Match": str(old)})
    print("   (task a changed, so its old tag is now stale:)")
    await call("PATCH", "/state/plan/a", {"overlap": {"x": "30 %", "y": "10 %"}}, headers={"If-Match": str(old)})
    await call("PATCH", "/state/plan/a", {"profiles": ["gfp"]}, headers={"If-Match": '"stale"'})
    await call("PATCH", "/state/writer", {"shard_z_chunks": 2}, headers={"If-Match": '"stale"'})
    await call("GET", "/no/such/route")
    print("== a body that is not JSON")
    status, _, answer = await asyncio.to_thread(_raw, "POST", "/state/plan", "{bad")
    print(f"POST   /state/plan  (body '{{bad')                -> {status}  {answer}")


if __name__ == "__main__":
    asyncio.run(main())
