import types
from collections.abc import Callable, Mapping
from typing import Annotated, Any, TypedDict, Unpack

import pytest
from pydantic import BaseModel, Field
from rigup.interface import action, create, delete, query, update
from vxlib.schema import Key

from vxl.station.instrument.interface import check_operations, route_of


class Item(BaseModel):
    id: Annotated[str, Key]
    size: int = 0


class Entry(BaseModel):
    size: int = 0


class Settings(BaseModel):
    level: int = 0


class Sub(BaseModel):
    items: list[Item] = []


class State(BaseModel):
    items: list[Item] = []
    entries: Mapping[Annotated[str, Field(min_length=1)], Entry] = {}
    settings: Settings = Settings()
    sub: Sub | None = None


class ItemFields(TypedDict, total=False):
    size: int


class WrongType(TypedDict, total=False):
    size: str


class Unknown(TypedDict, total=False):
    colour: str


class SettingsFields(TypedDict, total=False):
    level: int


def _fresh(function: Callable[..., Any]) -> Callable[..., Any]:
    """A copy of ``function``: a declaration is written on the function itself, so each case needs its own."""
    copy = types.FunctionType(function.__code__, function.__globals__, function.__name__, function.__defaults__)
    copy.__annotations__ = dict(function.__annotations__)
    return copy


def _check(**methods: Callable[..., Any]) -> dict[str, tuple[str, str]]:
    kind = type("Kind", (), methods)
    return {name: route_of(info, State) for name, info in check_operations(kind, State).items()}


async def _add(self: Any, item: Item) -> None: ...
async def _add_entry(self: Any, entry_id: str, entry: Entry) -> None: ...
async def _edit(self: Any, item_id: str, **fields: Unpack[ItemFields]) -> None: ...
async def _edit_settings(self: Any, **fields: Unpack[SettingsFields]) -> None: ...
async def _remove(self: Any, item_id: str) -> None: ...
async def _reorder(self: Any, item_ids: list[str]) -> None: ...
async def _start(self: Any) -> None: ...
async def _count(self: Any, item_id: str) -> int: ...


def test_each_operation_gets_its_route() -> None:
    routes = _check(
        add=create("items")(_fresh(_add)),
        add_entry=create("entries", key="entry_id")(_fresh(_add_entry)),
        edit=update("items", key="item_id")(_fresh(_edit)),
        edit_settings=update("settings")(_fresh(_edit_settings)),
        remove=delete("items", key="item_id")(_fresh(_remove)),
        remove_sub=delete("sub.items", key="item_id")(_fresh(_remove)),
        reorder=action(on="items", verb="reorder")(_fresh(_reorder)),
        start=action(on="preview", verb="start")(_fresh(_start)),
        count=query(on="items", key="item_id", verb="count")(_fresh(_count)),
        anything=action()(_fresh(_start)),
    )

    assert routes == {
        "add": ("POST", "/state/items"),
        "add_entry": ("POST", "/state/entries"),
        "edit": ("PATCH", "/state/items/{item_id}"),
        "edit_settings": ("PATCH", "/state/settings"),
        "remove": ("DELETE", "/state/items/{item_id}"),
        "remove_sub": ("DELETE", "/state/sub/items/{item_id}"),
        "reorder": ("POST", "/state/items:reorder"),
        "start": ("POST", "/preview:start"),
        "count": ("GET", "/state/items/{item_id}:count"),
        "anything": ("POST", "/instrument:anything"),
    }


async def _edit_wrong_key(self: Any, item_id: int, **fields: Unpack[ItemFields]) -> None: ...
async def _edit_wrong_type(self: Any, item_id: str, **fields: Unpack[WrongType]) -> None: ...
async def _edit_unknown(self: Any, item_id: str, **fields: Unpack[Unknown]) -> None: ...
async def _add_settings(self: Any, item: Settings) -> None: ...
async def _add_entry_no_key(self: Any, entry: Entry) -> None: ...
async def _add_item_with_key(self: Any, item_id: str, item: Item) -> None: ...


@pytest.mark.parametrize(
    ("methods", "message"),
    [
        ({"x": create("itemz")(_fresh(_add))}, "'itemz' is not in State"),
        ({"x": delete("settings", key="item_id")(_fresh(_remove))}, "'settings' is a single model, not a collection"),
        ({"x": update("items")(_fresh(_edit_settings))}, "needs a key: it is a collection"),
        ({"x": update("settings", key="item_id")(_fresh(_edit))}, "needs no key: it is a single model"),
        ({"x": update("items", key="item_id")(_fresh(_edit_wrong_key))}, "key 'item_id' is <class 'int'>"),
        ({"x": update("items", key="item_id")(_fresh(_edit_wrong_type))}, "'size' is <class 'str'> in WrongType"),
        ({"x": update("items", key="item_id")(_fresh(_edit_unknown))}, "Unknown names 'colour', which Item lacks"),
        ({"x": create("items")(_fresh(_add_settings))}, "adds a Settings, the collection holds Item"),
        ({"x": create("entries")(_fresh(_add_entry_no_key))}, "needs the new key as an argument"),
        ({"x": create("items", key="item_id")(_fresh(_add_item_with_key))}, "needs no key: items carry a Key"),
        (
            {
                "x": action(on="items", verb="reorder")(_fresh(_reorder)),
                "y": action(on="items", verb="reorder")(_fresh(_reorder)),
            },
            "both make POST /state/items:reorder",
        ),
    ],
)
def test_a_declaration_that_does_not_fit_the_state_fails(methods: dict[str, Callable[..., Any]], message: str) -> None:
    with pytest.raises(TypeError, match=message.replace("(", r"\(").replace(")", r"\)")):
        _check(**methods)
