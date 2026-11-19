"""Declarations beyond devices: resource intents, ``on``, ``key`` and ``verb``, and the checks a method alone shows."""

from collections.abc import Callable
from typing import Annotated, Any, NotRequired, TypedDict, Unpack

import pytest
from pydantic import BaseModel
from rigup.interface import (
    OperationInfo,
    action,
    bind_operations,
    create,
    delete,
    failsafe,
    operations_of,
    query,
    update,
)
from vxlib.schema import Key


class Item(BaseModel):
    id: Annotated[str, Key]
    name: str = ""


class ItemFields(TypedDict, total=False):
    name: str


class Required(TypedDict):
    name: str


class Qualified(TypedDict, total=False):
    name: NotRequired[str]


class Store:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @create("items")
    def add(self, item: Item) -> None:
        self.calls.append(("add", {"item": item}))

    @update("items", key="item_id")
    def edit(self, item_id: str, *, edit_id: str | None = None, **fields: Unpack[ItemFields]) -> None:
        self.calls.append(("edit", {"item_id": item_id, "edit_id": edit_id, **fields}))

    @delete("items", key="item_id")
    def remove(self, item_id: str) -> None:
        self.calls.append(("remove", {"item_id": item_id}))

    @action(on="preview", verb="start")
    def start_preview(self) -> None:
        self.calls.append(("start_preview", {}))

    @failsafe(on="preview", verb="stop")
    def stop_preview(self) -> None:
        self.calls.append(("stop_preview", {}))


def test_declarations_name_their_intent_resource_key_and_verb() -> None:
    found = {name: spec.info for name, spec in operations_of(Store).items()}

    assert {name: (i.intent, i.resource, i.key, i.verb) for name, i in found.items()} == {
        "add": ("create", "items", None, None),
        "edit": ("update", "items", "item_id", None),
        "remove": ("delete", "items", "item_id", None),
        "start_preview": ("action", "preview", None, "start"),
        "stop_preview": ("failsafe", "preview", None, "stop"),
    }
    assert set(found["edit"].params["properties"]) == {"item_id", "edit_id", "name"}


def test_an_update_gets_only_the_fields_that_were_sent() -> None:
    store = Store()
    edit = bind_operations(store)["edit"]

    edit(item_id="a", name="first")
    edit(item_id="a")

    assert store.calls == [
        ("edit", {"item_id": "a", "edit_id": None, "name": "first"}),
        ("edit", {"item_id": "a", "edit_id": None}),
    ]


def _kind(method: Callable[..., Any]) -> type:
    return type("Kind", (), {"x": method})


def _create_two(self: Any, item: Item, other: Item) -> None: ...
def _update_required(self: Any, item_id: str, **fields: Unpack[Required]) -> None: ...
def _update_extra(self: Any, item_id: str, force: bool, **fields: Unpack[ItemFields]) -> None: ...
def _update_no_fields(self: Any, item_id: str, name: str) -> None: ...
def _delete_extra(self: Any, item_id: str, force: bool) -> None: ...
def _key_default(self: Any, item_id: str = "a") -> None: ...
def _positional(self: Any, x: int, /) -> None: ...
def _no_self(x: int) -> None: ...
def _plain_kwargs(self: Any, **values: Any) -> None: ...
def _qualified(self: Any, item_id: str, **fields: Unpack[Qualified]) -> None: ...


@pytest.mark.parametrize(
    ("method", "message"),
    [
        (create("items")(_create_two), "takes the new item as 1 model argument"),
        (update("items", key="item_id")(_update_required), "every field of Required must be optional"),
        (update("items", key="item_id")(_update_extra), "also found ['force']"),
        (update("items", key="item_id")(_update_no_fields), "the fields come as **fields: Unpack[SomeFields]"),
        (delete("items", key="item_id")(_delete_extra), "takes only the key, also found ['force']"),
        (delete("items", key="item_id")(_key_default), "key 'item_id' must have no default"),
        (query()(_positional), "positional-only arguments are not allowed"),
        (query()(_no_self), "its first argument is self"),
        (action()(_plain_kwargs), "**fields must be **fields: Unpack[SomeTypedDict]"),
    ],
)
def test_a_declaration_that_breaks_a_rule_fails_when_the_class_is_read(
    method: Callable[..., Any], message: str
) -> None:
    with pytest.raises(TypeError, match=message.replace("[", r"\[").replace("*", r"\*")):
        operations_of(_kind(method))


def test_a_required_qualifier_inside_the_fields_is_understood() -> None:
    assert "name" in operations_of(_kind(update("items", key="item_id")(_qualified)))["x"].info.params["properties"]


def test_a_key_that_is_not_an_argument_fails_at_the_decorator() -> None:
    with pytest.raises(TypeError, match="key 'nope' is not an argument"):
        delete("items", key="nope")(_delete_extra)


def test_an_override_cannot_change_what_an_operation_does() -> None:
    class Base:
        @action(on="preview", verb="start")
        def go(self) -> None: ...

    class Changed(Base):
        @action(on="preview", verb="begin")
        def go(self) -> None: ...

    with pytest.raises(TypeError, match="is declared @action\\(on='preview', verb='begin'\\), but Base says"):
        operations_of(Changed)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"intent": "update"}, "a update names its resource"),
        ({"intent": "delete", "resource": "items"}, "a delete names its key"),
        ({"intent": "update", "resource": "items", "verb": "edit"}, "a update has no verb"),
    ],
)
def test_operation_info_refuses_fields_that_do_not_fit_the_intent(fields: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        OperationInfo(name="x", label="X", **fields)
