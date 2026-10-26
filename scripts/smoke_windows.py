"""Launch a frozen Windows app without Python/Qt paths from the build environment.

This checks the actual executable twice. It never compiles an application and is
intended to be run on the native Windows machine that produced the executable.
"""

from __future__ import annotations

import argparse
import json
import ntpath
import os
import struct
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def require_windows_x64() -> None:
    if sys.platform != "win32":
        raise RuntimeError(
            "Windows executable validation requires native Windows; Linux is unsupported."
        )
    if struct.calcsize("P") != 8:
        raise RuntimeError("Use 64-bit Python to validate the Windows x64 executable.")


def isolated_environment(appdata: Path, local_appdata: Path) -> dict[str, str]:
    """Preserve OS variables but remove Python and Qt search-path dependencies."""
    excluded = {
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "__PYVENV_LAUNCHER__",
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QML_IMPORT_PATH",
        "QML2_IMPORT_PATH",
        "_MEIPASS2",
    }
    environment = {
        key.upper(): value
        for key, value in os.environ.items()
        if key.upper() not in excluded and not key.upper().startswith(("PYTHON", "_PYI_"))
    }
    windows = environment.get("SYSTEMROOT") or environment.get("WINDIR") or r"C:\Windows"
    environment["PATH"] = ";".join(
        [ntpath.join(windows, "System32"), windows, ntpath.join(windows, "System32", "Wbem")]
    )
    environment["APPDATA"] = str(appdata)
    environment["LOCALAPPDATA"] = str(local_appdata)
    # Exercise the native Windows platform plugin, rather than a headless plugin.
    environment["QT_QPA_PLATFORM"] = "windows"
    return environment


def _under_directory(value: object, directory: Path) -> bool:
    if not isinstance(value, str):
        return False
    try:
        Path(value).resolve().relative_to(directory.resolve())
    except (OSError, ValueError):
        return False
    return True


def validate_report(report: Mapping[str, Any], appdata: Path, *, second_run: bool) -> None:
    """Reject source-mode runs, missing dependencies, or nonpersistent settings."""
    required = {
        "status": "passed",
        "frozen": True,
        "platform": "win32",
        "qt_platform": "windows",
        "ui_constructed": True,
        "settings_roundtrip": True,
        "nvml_binding_available": True,
    }
    for key, expected in required.items():
        if type(report.get(key)) is not type(expected) or report.get(key) != expected:
            raise RuntimeError(f"Frozen application self-test failed: {key} must be {expected!r}.")
    if report.get("errors") != []:
        raise RuntimeError("Frozen application self-test reported errors.")
    for field in ("settings_path", "persistence_probe_path"):
        if not _under_directory(report.get(field), appdata):
            raise RuntimeError(
                f"Self-test {field} must be in the isolated per-user APPDATA folder."
            )
    probe = Path(report["persistence_probe_path"])
    try:
        saved = json.loads(probe.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("Self-test did not persist its settings probe to APPDATA.") from exc
    if not isinstance(saved, dict) or saved.get("profile") != "Eco":
        raise RuntimeError("Self-test settings probe contains incorrect persisted settings.")
    if second_run:
        previous = report.get("previous_settings")
        if not isinstance(previous, dict) or previous.get("profile") != "Eco":
            raise RuntimeError("Settings did not survive relaunch of the standalone executable.")


def smoke_executable(executable: Path, mode: str, reports_dir: Path) -> None:
    require_windows_x64()
    executable = executable.resolve()
    if not executable.is_file():
        raise RuntimeError(f"Built executable is missing: {executable}")
    reports_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"nexus-{mode}-smoke-") as temporary:
        scratch = Path(temporary)
        appdata = scratch / "AppData" / "Roaming"
        local_appdata = scratch / "AppData" / "Local"
        working_dir = scratch / "unrelated-working-directory"
        for directory in (appdata, local_appdata, working_dir):
            directory.mkdir(parents=True)
        environment = isolated_environment(appdata, local_appdata)
        for index, label in enumerate(("first", "second")):
            report_path = reports_dir / f"{mode}-{label}.json"
            log_path = reports_dir / f"{mode}-{label}.log"
            report_path.unlink(missing_ok=True)
            command = [
                str(executable),
                "--self-test",
                "--self-test-report",
                str(report_path.resolve()),
            ]
            try:
                result = subprocess.run(
                    command,
                    cwd=working_dir,
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=120,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                log_path.write_text(
                    "Frozen application exceeded the 120-second timeout.\n", "utf-8"
                )
                raise RuntimeError(f"Standalone {mode} self-test timed out.") from exc
            log_path.write_text(
                f"Exit code: {result.returncode}\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
                encoding="utf-8",
            )
            if result.returncode != 0:
                raise RuntimeError(f"Standalone {mode} self-test failed. See {log_path}.")
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise RuntimeError(
                    f"Standalone {mode} did not write a valid self-test report."
                ) from exc
            if not isinstance(report, dict):
                raise RuntimeError("Standalone self-test report must contain a JSON object.")
            validate_report(report, appdata, second_run=index == 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--mode", choices=("onefile", "onedir"), required=True)
    parser.add_argument("--reports-dir", type=Path, default=Path("dist/smoke"))
    args = parser.parse_args(argv)
    try:
        smoke_executable(args.executable, args.mode, args.reports_dir)
    except (OSError, RuntimeError) as exc:
        parser.exit(1, f"{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
