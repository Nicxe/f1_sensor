from __future__ import annotations

from types import SimpleNamespace

from custom_components.f1_sensor.sensor import F1DriverPositionsSensor


class DummyCoordinator(SimpleNamespace):
    def async_add_listener(self, _listener):
        return lambda: None


def _make_sensor() -> F1DriverPositionsSensor:
    coord = DummyCoordinator(data={})
    return F1DriverPositionsSensor(coord, "F1", "uid", "entry", "F1")


def test_driver_status_pit_out_hold() -> None:
    sensor = _make_sensor()
    timing = {
        "pit_out": True,
        "in_pit": False,
        "retired": False,
        "stopped": False,
    }

    status, attrs = sensor._derive_driver_status("1", timing, now=0.0)
    assert status == "pit_out"
    assert attrs["pit_out"] is True

    timing["pit_out"] = False
    status, attrs = sensor._derive_driver_status("1", timing, now=3.0)
    assert status == "pit_out"
    assert attrs["pit_out"] is True

    status, attrs = sensor._derive_driver_status("1", timing, now=10.0)
    assert status == "on_track"
    assert attrs["pit_out"] is False


def test_driver_status_out_priority() -> None:
    sensor = _make_sensor()
    timing = {
        "pit_out": True,
        "in_pit": True,
        "retired": True,
        "stopped": False,
    }

    status, attrs = sensor._derive_driver_status("10", timing, now=1.0)
    assert status == "out"
    assert attrs["retired"] is True


def test_driver_status_on_track() -> None:
    sensor = _make_sensor()
    timing = {
        "in_pit": False,
        "retired": False,
        "stopped": False,
    }

    status, attrs = sensor._derive_driver_status("44", timing, now=5.0)
    assert status == "on_track"
    assert attrs["in_pit"] is False
    assert attrs["pit_out"] is False


def test_driver_status_unknown_without_timing() -> None:
    sensor = _make_sensor()
    status, attrs = sensor._derive_driver_status("77", None, now=5.0)
    assert status is None
    assert attrs["pit_out"] is None


def test_driver_status_default_on_track_for_replay() -> None:
    sensor = _make_sensor()
    status, attrs = sensor._derive_driver_status(
        "1", None, now=0.0, default_on_track=True
    )
    assert status == "on_track"
    assert attrs["in_pit"] is False
    assert attrs["pit_out"] is False
    assert attrs["retired"] is False
    assert attrs["stopped"] is False


def test_driver_status_default_on_track_with_partial_timing() -> None:
    sensor = _make_sensor()
    timing = {"in_pit": None}
    status, attrs = sensor._derive_driver_status(
        "1", timing, now=0.0, default_on_track=True
    )
    assert status == "on_track"
    assert attrs["in_pit"] is False
    assert attrs["pit_out"] is False
    assert attrs["retired"] is False
    assert attrs["stopped"] is False
