"""Exercise the CI parent deadline against actual child Python processes."""

from __future__ import annotations

import importlib
import time
from pathlib import Path

import pytest


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("run_tests")


def test_parent_preserves_passing_failing_and_environment_results(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_RUNNER_TEST", "inherited")
    passing = tmp_path / "test_pass.py"
    passing.write_text(
        "import os\ndef test_environment():\n"
        "    assert os.environ['NEXUS_RUNNER_TEST'] == 'inherited'\n",
        encoding="utf-8",
    )
    assert runner.run_tests([str(passing)], timeout_seconds=20) == 0
    failing = tmp_path / "test_fail.py"
    failing.write_text("def test_failure():\n    assert False\n", encoding="utf-8")
    assert runner.run_tests([str(failing)], timeout_seconds=20) == 1


def test_parent_terminates_a_hanging_test_interpreter(runner, tmp_path, capsys):
    hanging = tmp_path / "test_hang.py"
    hanging.write_text("import time\ndef test_hang():\n    time.sleep(60)\n", encoding="utf-8")
    started = time.monotonic()
    assert runner.run_tests([str(hanging)], timeout_seconds=0.5) == 124
    assert time.monotonic() - started < 10
    assert "test interpreter was terminated" in capsys.readouterr().err
