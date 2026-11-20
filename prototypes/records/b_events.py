"""Records design B: an event log, and the record worked out from it.

The acquisition loop appends events. The store keeps them in order, 1 row each, and never changes a row. The record
is what 1 function, ``fold``, makes of the events: it is the only place with rules. ``acquisition.json`` is the fold
written out; live readers can follow the events themselves, with ``seq`` as their cursor.

Run: ``uv run python -m prototypes.records.b_events``
"""

import asyncio
import datetime
from collections import defaultdict
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import Field, TypeAdapter
from vxlib.issues import Failure
from vxlib.schema import FrozenModel
from vxlib.vector import Transform

from vxl.storage import ImageLocation

from .scenario import CAMERA_LOCATION, TRANSFORM, show

# --- the events: what happened, in the loop's words ---


class Planned(FrozenModel):
    """The first event: the visits, and each camera's image, frozen at Start."""

    type: Literal["planned"] = "planned"
    visits: list[tuple[str, str, dict[str, Transform]]]  # task, profile, transform by camera


class Started(FrozenModel):
    type: Literal["started"] = "started"


class VisitStarted(FrozenModel):
    type: Literal["visit_started"] = "visit_started"
    visit: int
    locations: dict[str, ImageLocation]


class FramesWritten(FrozenModel):
    type: Literal["frames_written"] = "frames_written"
    visit: int
    camera: str
    written: int


class VisitEnded(FrozenModel):
    type: Literal["visit_ended"] = "visit_ended"
    visit: int
    result: Literal["completed", "failed", "cancelled"]
    failures: list[Failure] = Field(default_factory=list)


class Ended(FrozenModel):
    type: Literal["ended"] = "ended"
    result: Literal["completed", "failed", "cancelled", "interrupted"]
    failures: list[Failure] = Field(default_factory=list)


type Event = Annotated[
    Planned | Started | VisitStarted | FramesWritten | VisitEnded | Ended, Field(discriminator="type")
]
_EVENT = TypeAdapter[Event](Event)


class Logged(FrozenModel):
    seq: int
    at: datetime.datetime
    event: Event


# --- the store: append only ---


class EventStore:
    def __init__(self) -> None:
        self.rows: dict[UUID, list[Logged]] = defaultdict(list)

    async def append(self, acquisition_id: UUID, event: Event) -> Logged:
        rows = self.rows[acquisition_id]  # SQLite: 1 INSERT into events (acquisition_id, seq, at, event_json)
        logged = Logged(seq=len(rows) + 1, at=datetime.datetime.now(tz=datetime.UTC), event=event)
        rows.append(logged)
        return logged


# --- the 1 place with rules: the record worked out from the events ---


class ImageView(FrozenModel):
    status: str
    frames_written: int
    frames_total: int
    locations: list[ImageLocation]


class VisitView(FrozenModel):
    task: str
    profile: str
    status: str
    failures: list[Failure]
    images: dict[str, ImageView]


class AcquisitionView(FrozenModel):
    status: str
    failures: list[Failure]
    visits: list[VisitView]
    seq: int


def fold(events: list[Logged]) -> AcquisitionView:
    """The record that ``events`` describe. An event that cannot follow the ones before it raises ``ValueError``."""
    first = events[0].event
    if not isinstance(first, Planned):
        raise ValueError("the first event must be 'planned'")
    status, failures = "preparing", list[Failure]()
    visits = [
        {"status": "pending", "failures": [], "written": dict.fromkeys(t, 0), "loc": {}} for _, _, t in first.visits
    ]
    for logged in events[1:]:
        match logged.event:
            case Started() if status == "preparing":
                status = "running"
            case VisitStarted(visit=i, locations=loc) if status == "running" and visits[i]["status"] == "pending":
                visits[i] |= {"status": "running", "loc": loc}
            case FramesWritten(visit=i, camera=c, written=n) if visits[i]["status"] == "running":
                visits[i]["written"][c] = n
            case VisitEnded(visit=i, result=r, failures=f) if visits[i]["status"] == "running":
                visits[i] |= {"status": r, "failures": f}
            case Ended(result=r, failures=f) if status in {"preparing", "running"}:
                status, failures = r, f
                for v in visits:
                    v["status"] = "skipped" if v["status"] == "pending" else v["status"]
            case other:
                raise ValueError(f"event {logged.seq} ({other.type}) cannot follow the ones before it")

    def image(v: dict, camera: str, transform: Transform) -> ImageView:
        written, total = v["written"][camera], transform.shape[0]
        if written == total:
            state = "completed"
        elif v["status"] == "skipped":
            state = "skipped"
        elif v["status"] in {"pending", "running"}:
            state = "writing" if camera in v["loc"] else "pending"
        else:
            state = "partial" if written else "failed"
        locations = [v["loc"][camera]] if camera in v["loc"] else []
        return ImageView(status=state, frames_written=written, frames_total=total, locations=locations)

    return AcquisitionView(
        status=status,
        failures=failures,
        visits=[
            VisitView(
                task=task,
                profile=profile,
                status=v["status"],
                failures=v["failures"],
                images={cam: image(v, cam, t) for cam, t in transforms.items()},
            )
            for (task, profile, transforms), v in zip(first.visits, visits, strict=True)
        ],
        seq=events[-1].seq,
    )


async def main() -> None:
    store, acquisition = EventStore(), uuid4()
    lost = Failure.of(TimeoutError("camera stopped sending"), code="acquisition.frames_lost", loc=("camera",))
    for event in [
        Planned(visits=[("brain", "gfp", {"camera": TRANSFORM})] * 3),
        Started(),
        VisitStarted(visit=0, locations={"camera": CAMERA_LOCATION}),
        FramesWritten(visit=0, camera="camera", written=10),
        VisitEnded(visit=0, result="completed"),
        VisitStarted(visit=1, locations={"camera": CAMERA_LOCATION}),
        FramesWritten(visit=1, camera="camera", written=4),
        VisitEnded(visit=1, result="failed", failures=[lost]),
        Ended(result="failed", failures=[lost]),
    ]:
        await store.append(acquisition, event)

    view = fold(store.rows[acquisition])
    show(
        "B",
        view.status,
        [(v.status, v.images["camera"].status, v.images["camera"].frames_written) for v in view.visits],
        f"{view.seq} events",
    )

    try:
        fold([*store.rows[acquisition], Logged(seq=99, at=datetime.datetime.now(tz=datetime.UTC), event=Started())])
    except ValueError as error:
        print(f"  a wrong event: {error}")
    print(f"  an event as JSON: {_EVENT.dump_json(store.rows[acquisition][3].event).decode()}")


if __name__ == "__main__":
    asyncio.run(main())
