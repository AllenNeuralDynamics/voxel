import pytest
from pydantic import BaseModel, ValidationError
from rigur.build import BuildConfig, dependencies
from rigur.config import NodeConfig, RigConfig
from rigur.device.results import CommandRequest
from rigur.node._protocol import BuildDevicesRequest

from rigur import Part

MAIN = {
    "parts": {"glass": {"kind": "filter"}},
    "devices": {"camera": {"target": "some.Camera", "details": {"vendor": "ACME"}}},
}
NESTED = {
    "parts": {"glass": {"target": "rigur_fakes.MockPart", "value": 1.5, "details": {"serial": "42"}}},
    "devices": {"camera": {"target": "some.Camera"}},
    "nodes": {
        "detection": {
            "address": "tcp://10.0.0.2:5555",
            "devices": {"wheel": {"target": "some.Wheel", "init": {"slots": {"0": "glass"}}}},
        },
    },
}


def test_an_empty_rig_has_no_components() -> None:
    config = RigConfig.model_validate({})

    assert (config.nodes, config.devices, config.parts) == ({}, {}, {})


def test_top_level_devices_belong_to_no_node() -> None:
    config = RigConfig.model_validate(MAIN)

    assert config.nodes == {}
    assert set(config.devices) == set(config.all_devices) == {"camera"}
    assert set(config.parts) == {"glass"}


def test_a_rig_keeps_its_nodes() -> None:
    config = RigConfig.model_validate(NESTED)

    assert set(config.nodes) == {"detection"}
    assert config.nodes["detection"].kind == "remote"
    assert config.nodes["detection"].address == "tcp://10.0.0.2:5555"
    assert set(config.devices) == {"camera"}
    assert set(config.all_devices) == {"camera", "wheel"}


def test_a_rig_survives_a_json_roundtrip() -> None:
    config = RigConfig.model_validate(NESTED)

    restored = RigConfig.model_validate(config.model_dump(mode="json"))

    assert restored == config


def test_parts_survive_a_build_request_roundtrip() -> None:
    config = RigConfig.model_validate_json(RigConfig.model_validate(NESTED).model_dump_json())
    request = BuildDevicesRequest(devices=config.nodes["detection"].devices, parts=config.parts)

    received = BuildDevicesRequest.model_validate_json(request.model_dump_json())

    assert received.parts == config.parts
    assert type(received.parts["glass"]).__name__ == "MockPart"
    assert received.parts["glass"].details == {"serial": "42"}


@pytest.mark.parametrize(
    ("uid", "location"),
    [
        ("glass", ("parts", "glass")),
        ("camera", ("devices", "camera")),
        ("wheel", ("nodes", "detection", "devices", "wheel")),
    ],
    ids=["part", "device", "node-device"],
)
def test_component_location_says_where_a_component_is_written(uid: str, location: tuple[str, ...]) -> None:
    config = RigConfig.model_validate(NESTED)

    assert config.component_location(uid) == location


def test_a_part_with_a_target_is_made_from_that_class() -> None:
    glass = RigConfig.model_validate(NESTED).parts["glass"]

    assert (type(glass).__name__, glass.uid, glass.kind) == ("MockPart", "glass", "mock_part")


def test_a_part_without_a_target_is_a_plain_part() -> None:
    glass = RigConfig.model_validate(MAIN).parts["glass"]

    assert (type(glass), glass.uid, glass.kind) == (Part, "glass", "filter")


@pytest.mark.parametrize("raw", [NESTED, MAIN], ids=["targeted", "plain"])
def test_a_part_is_written_back_as_its_fields(raw: dict[str, object]) -> None:
    dumped = RigConfig.model_validate(raw).model_dump(mode="json")

    assert dumped["parts"] == raw["parts"]


def test_each_bad_part_is_a_problem_at_its_field() -> None:
    raw = {
        "parts": {
            "a": {"target": "rigur_fakes.MockPart", "value": "high"},
            "b": {"kind": "filter", "band": [500, 550]},
            "c": {"target": "rigur_fakes.NoSuchPart", "kind": "x"},
        }
    }

    with pytest.raises(ValidationError) as caught:
        RigConfig.model_validate(raw)

    assert [error["loc"] for error in caught.value.errors()] == [
        ("parts", "a", "value"),
        ("parts", "b", "band"),
        ("parts", "c"),
    ]


def test_each_rig_problem_has_its_code_and_its_place() -> None:
    raw = {
        "parts": {"camera": {"kind": "spot"}, "glass": {"kind": "filter"}},
        "devices": {"camera": {"target": "some.Camera"}},
        "nodes": {
            "detection": {
                "kind": "subprocess",
                "devices": {"wheel": {"target": "some.Wheel", "init": {"hub": "hub", "slot": "glass"}}},
            },
            "motion": {"kind": "subprocess", "devices": {"hub": {"target": "some.Hub"}}},
        },
    }

    with pytest.raises(ValidationError) as caught:
        RigConfig.model_validate(raw)

    assert [(error["type"], error["loc"]) for error in caught.value.errors()] == [
        ("duplicate_uid", ("devices", "camera")),
        ("cross_node_reference", ("nodes", "detection", "devices", "wheel")),
    ]


def test_a_remote_node_without_an_address_is_a_problem_at_its_address() -> None:
    raw = {"nodes": {"near": {"address": None, "kind": "remote"}, "far": {"kind": "remote"}}}

    with pytest.raises(ValidationError) as caught:
        RigConfig.model_validate(raw)

    assert [(error["type"], error["loc"]) for error in caught.value.errors()] == [
        ("remote_node_address", ("nodes", "near", "address")),
        ("remote_node_address", ("nodes", "far", "address")),
    ]


def test_a_device_uid_used_on_two_nodes_is_refused() -> None:
    raw = {
        "devices": {"camera": {"target": "some.Camera"}},
        "nodes": {"remote": {"kind": "subprocess", "devices": {"camera": {"target": "some.OtherCamera"}}}},
    }

    with pytest.raises(ValidationError, match="Component UID 'camera' is duplicated"):
        RigConfig.model_validate(raw)


def test_a_device_may_name_a_device_on_its_own_node() -> None:
    raw = {
        "nodes": {
            "motion": {
                "kind": "subprocess",
                "devices": {"hub": {"target": "some.Hub"}, "axis": {"target": "some.Axis", "init": {"hub": "hub"}}},
            }
        }
    }

    config = RigConfig.model_validate(raw)

    assert config.nodes["motion"].devices["axis"].init["hub"] == "hub"


def test_a_device_naming_a_device_on_another_node_is_refused() -> None:
    raw = {
        "nodes": {
            "motion": {"kind": "subprocess", "devices": {"hub": {"target": "some.Hub"}}},
            "camera": {
                "kind": "subprocess",
                "devices": {
                    "camera": {"target": "some.Camera", "init": {"trigger_source": {"devices": ["hub"]}}},
                },
            },
        }
    }

    with pytest.raises(ValidationError, match="constructor-injected dependencies must be in the same process"):
        RigConfig.model_validate(raw)


@pytest.mark.parametrize(
    ("uid", "expected"),
    [("hub", set()), ("axis", {"hub"}), ("pair", {"axis", "hub"})],
    ids=["none", "direct", "nested"],
)
def test_dependencies_are_the_devices_that_init_names(uid: str, expected: set[str]) -> None:
    config = RigConfig.model_validate(
        {
            "devices": {
                "hub": {"target": "some.Hub", "init": {"port": "COM4"}},
                "axis": {"target": "some.Axis", "init": {"hub": "hub", "label": "axis"}},
                "pair": {"target": "some.Pair", "init": {"members": {"first": ["axis"], "second": "hub"}}},
            }
        }
    )

    assert dependencies(config.devices, uid) == expected


def test_an_empty_nodes_value_is_refused() -> None:
    with pytest.raises(ValidationError, match="valid dictionary"):
        RigConfig.model_validate({"nodes": None})


@pytest.mark.parametrize(
    ("model", "raw"),
    [
        (RigConfig, {"name": "test"}),
        (NodeConfig, {"kind": "subprocess", "adress": "tcp://localhost:5555"}),
        (BuildConfig, {"target": "some.Module", "initial": {}}),
        (CommandRequest, {"attr": "enable", "arguments": []}),
    ],
    ids=["rig", "node", "build", "command-request"],
)
def test_an_unknown_field_is_refused(model: type[BaseModel], raw: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        model.model_validate(raw)


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        ({"devices": {}}, "subprocess"),
        ({"address": "tcp://localhost:5555"}, "subprocess"),
        ({"address": "tcp://127.0.0.1:5555"}, "subprocess"),
        ({"address": "tcp://[::1]:5555"}, "subprocess"),
        ({"address": "tcp://*:5555"}, "subprocess"),
        ({"address": "ipc:///tmp/test"}, "subprocess"),
        ({"address": "tcp://10.0.0.2:5555"}, "remote"),
        ({"kind": "remote", "address": "tcp://localhost:5555"}, "remote"),
    ],
    ids=["no-address", "localhost", "loopback", "ipv6-loopback", "bind-any", "ipc", "remote-host", "explicit-kind"],
)
def test_node_kind_follows_the_address(raw: dict[str, object], kind: str) -> None:
    assert NodeConfig.model_validate(raw).kind == kind


@pytest.mark.parametrize("address", [None, "tcp://localhost:5555"], ids=["without-address", "with-address"])
def test_a_subprocess_node_keeps_its_address(address: str | None) -> None:
    node = NodeConfig.model_validate({"kind": "subprocess", "address": address})

    assert node.address == address


def test_a_node_is_never_local() -> None:
    with pytest.raises(ValidationError, match="Input should be 'subprocess' or 'remote'"):
        NodeConfig.model_validate({"kind": "local"})


def test_a_remote_node_needs_an_address() -> None:
    with pytest.raises(ValidationError, match="address"):
        NodeConfig.model_validate({"kind": "remote"})
