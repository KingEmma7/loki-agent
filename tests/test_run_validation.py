import pytest
from click import unstyle
from typer.testing import CliRunner

from loki import cli
from loki.cli import app
from loki.services.run import RunSetupError


@pytest.fixture
def captured(monkeypatch):
    """Replaces prepare_run so no browser starts; records the options it was given."""
    seen = {}

    def capture_and_stop(options):
        seen["options"] = options
        raise RunSetupError("stop before launching a browser")

    monkeypatch.setattr(cli, "prepare_run", capture_and_stop)
    return seen


def _invoke(*args):
    # Rich ignores COLUMNS for dumb terminals when CI forces terminal rendering.
    runner = CliRunner(env={"NO_COLOR": "1", "TERM": "xterm", "COLUMNS": "200"})
    return runner.invoke(app, ["run", "http://localhost:8000", *args])


@pytest.mark.parametrize("value", ["0", "-5"])
def test_run_rejects_duration_below_one(captured, value):
    result = _invoke("--duration", value)
    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert "options" not in captured


@pytest.mark.parametrize("value", ["-0.1", "1.5", "42"])
def test_run_rejects_fault_rate_outside_probability_range(captured, value):
    result = _invoke("--fault-rate", value)
    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert "options" not in captured


@pytest.mark.parametrize(
    ("args", "duration", "fault_rate"),
    [
        (["--duration", "1", "--fault-rate", "0"], 1, 0.0),
        (["--duration", "30", "--fault-rate", "0.65"], 30, 0.65),
        (["--fault-rate", "1"], None, 1.0),
        ([], None, None),
    ],
)
def test_run_accepts_valid_duration_and_fault_rate(captured, args, duration, fault_rate):
    result = _invoke(*args)
    # prepare_run is stubbed to stop with exit code 1, after the arguments were parsed.
    assert result.exit_code == 1
    assert captured["options"].duration == duration
    assert captured["options"].fault_rate == fault_rate


@pytest.mark.parametrize("value", ["landcape", "sideways", "", " landscape "])
def test_run_rejects_invalid_orientation(captured, value):
    result = _invoke("--orientation", value)
    output = unstyle(result.output)
    assert result.exit_code == 2
    assert "Invalid value for '--orientation'" in output
    assert "'portrait'" in output
    assert "'landscape'" in output
    assert "options" not in captured


@pytest.mark.parametrize(
    ("args", "orientation"),
    [
        ([], "portrait"),
        (["--orientation", "portrait"], "portrait"),
        (["--orientation", "landscape"], "landscape"),
        (["--orientation", "PORTRAIT"], "portrait"),
        (["--orientation", "LANDSCAPE"], "landscape"),
        (["--orientation", "Portrait"], "portrait"),
        (["--orientation", "Landscape"], "landscape"),
    ],
)
def test_run_accepts_valid_orientation(captured, args, orientation):
    result = _invoke("--device", "iphone-15", *args)
    assert result.exit_code == 1
    options = captured["options"]
    assert options.device == "iphone-15"
    assert type(options.orientation) is str
    assert options.orientation == orientation


def test_run_help_lists_orientation_choices(captured):
    result = _invoke("--help")
    output = unstyle(result.output)
    assert result.exit_code == 0
    orientation_line = next(line for line in output.splitlines() if "--orientation" in line)
    assert "portrait|landscape" in orientation_line
    assert "options" not in captured
