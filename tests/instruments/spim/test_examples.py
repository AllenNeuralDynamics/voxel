import pytest

from .support import FILES, load_file


@pytest.mark.parametrize(
    ("name", "starters", "waits"),
    [
        ("exaspim-v1.yaml", ("ao_main",), {"camera": "ao_main.camera_trigger", "z_axis": "ao_main.z_step"}),
        ("exaspim-v1-sweep-ao-main.yaml", ("ao_main",), {"camera": "ao_main.camera_trigger"}),
        (
            "exaspim-v1-sweep-z-axis.yaml",
            ("z_axis",),
            {"ao_main": "z_axis.z_pulse", "camera": "ao_main.camera_trigger"},
        ),
        ("open-top.yaml", ("x_axis",), {"ao_main": "x_axis.x_pulse", "camera": "ao_main.camera_trigger"}),
    ],
)
def test_an_example_file_has_no_problems_and_a_full_chain(
    name: str, starters: tuple[str, ...], waits: dict[str, str]
) -> None:
    file = load_file(FILES / name)
    assert file.problems() == []

    for profile in file.default.profiles.values():
        chain = profile.trigger_chain(file.config)
        assert chain.starters == starters
        assert {device: f"{wire.sender}.{wire.name}" for device, wire in chain.waits.items()} == waits
        assert chain.unstarted == ()
