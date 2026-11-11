import pytest

from vxl.hal_next.signals import Timeline


def test_windows_follow_the_edges_they_name() -> None:
    timeline = Timeline.model_validate(
        {
            "sample_rate": "10 kHz",
            "duration": "100 ms",
            "signals": {
                "camera": {
                    "kind": "on",
                    "start": {"timeline": "start", "offset": "10 ms"},
                    "end": {"signal": "camera", "edge": "start", "offset": "50 ms"},
                },
                "laser": {
                    "kind": "on",
                    "start": {"signal": "camera", "edge": "start", "offset": "-5 ms"},
                    "end": {"timeline": "end", "offset": "-10 ms"},
                },
                "copy": {"kind": "follow", "source": "laser", "delay": "2 ms"},
            },
        }
    )
    windows = timeline.windows()
    assert windows["camera"] == pytest.approx((0.01, 0.06))
    assert windows["laser"] == pytest.approx((0.005, 0.09))
    assert windows["copy"].a == pytest.approx(0.007)
