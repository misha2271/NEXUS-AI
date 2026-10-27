"""Validate Windows build orchestration without compiling Windows code on Linux."""

from __future__ import annotations

import importlib
import json
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def scripts(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return (
        importlib.import_module("build_windows"),
        importlib.import_module("smoke_windows"),
    )


def make_onedir(directory):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "NEXUS-AI.exe").write_bytes(b"test fixture, not an executable")
    plugins = directory / "_internal" / "PySide6" / "plugins" / "platforms"
    plugins.mkdir(parents=True)
    (plugins / "qwindows.dll").write_bytes(b"test fixture")
    (directory / "_internal" / "python312.dll").write_bytes(b"test fixture")


def report_fixture(appdata, *, previous_profile="Smart"):
    config = appdata / "NEXUS AI"
    config.mkdir(parents=True, exist_ok=True)
    probe = config / ".packaging-self-test.json"
    probe.write_text(json.dumps({"profile": "Eco", "model": ""}), encoding="utf-8")
    return {
        "status": "passed",
        "errors": [],
        "frozen": True,
        "platform": "win32",
        "qt_platform": "windows",
        "ui_constructed": True,
        "settings_roundtrip": True,
        "nvml_binding_available": True,
        "languages_tested": ["ru", "en"],
        "language_persistence": True,
        "settings_path": str(config / "settings.json"),
        "persistence_probe_path": str(probe),
        "previous_settings": {"profile": previous_profile, "model": ""},
    }


def test_linux_refusal_happens_before_dependency_checks_or_processes(
    scripts, monkeypatch, tmp_path
):
    build, smoke = scripts
    calls = []
    monkeypatch.setattr(smoke.sys, "platform", "linux")
    monkeypatch.setattr(build, "_check_dependencies", lambda: calls.append("dependencies"))
    monkeypatch.setattr(build.subprocess, "run", lambda *args, **kwargs: calls.append("process"))
    with pytest.raises(RuntimeError, match="native Windows"):
        build.build("both", tmp_path)
    assert calls == []
    assert list(tmp_path.iterdir()) == []


def test_32bit_python_is_rejected(scripts, monkeypatch):
    _build, smoke = scripts
    monkeypatch.setattr(smoke.sys, "platform", "win32")
    monkeypatch.setattr(smoke.struct, "calcsize", lambda _format: 4)
    with pytest.raises(RuntimeError, match="64-bit Python"):
        smoke.require_windows_x64()


def test_pyinstaller_configuration_covers_dynamic_and_qt_dependencies(scripts, tmp_path):
    build, _smoke = scripts
    for mode in build.MODES:
        command = build.pyinstaller_command(tmp_path, mode)
        assert command[:3] == [build.sys.executable, "-m", "PyInstaller"]
        assert f"--{mode}" in command
        assert "--windowed" in command
        assert "--noupx" in command
        for dependency in (
            "PySide6.QtCore",
            "PySide6.QtGui",
            "PySide6.QtWidgets",
            "pynvml",
            "psutil._psutil_windows",
            "sqlite3",
            "ssl",
            "http.server",
            "ctypes",
        ):
            position = command.index(dependency)
            assert command[position - 1] == "--hidden-import"
        assert command[command.index("certifi") - 1] == "--collect-data"
        assert command[-1] == str(tmp_path / "packaging" / "windows" / "entrypoint.py")
        assert str(tmp_path / "dist" / mode) in command
    with pytest.raises(ValueError, match="Unsupported"):
        build.pyinstaller_command(tmp_path, "linux")


def test_portable_zip_preserves_all_runtime_files_in_one_root(scripts, tmp_path):
    build, _smoke = scripts
    directory = tmp_path / "onedir" / "NEXUS-AI"
    make_onedir(directory)
    output = tmp_path / "portable.zip"
    build.archive_onedir(directory, output)
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert names == {
            "NEXUS-AI/NEXUS-AI.exe",
            "NEXUS-AI/_internal/PySide6/plugins/platforms/qwindows.dll",
            "NEXUS-AI/_internal/python312.dll",
        }
        assert archive.testzip() is None


def test_portable_zip_is_not_created_without_windows_platform_plugin(scripts, tmp_path):
    build, _smoke = scripts
    directory = tmp_path / "NEXUS-AI"
    make_onedir(directory)
    (directory / "_internal" / "PySide6" / "plugins" / "platforms" / "qwindows.dll").unlink()
    output = tmp_path / "portable.zip"
    with pytest.raises(RuntimeError, match="qwindows.dll"):
        build.archive_onedir(directory, output)
    assert not output.exists()


def test_zip_write_failure_removes_incomplete_archive(scripts, monkeypatch, tmp_path):
    build, _smoke = scripts
    directory = tmp_path / "NEXUS-AI"
    make_onedir(directory)
    output = tmp_path / "portable.zip"

    def fail_write(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(zipfile.ZipFile, "write", fail_write)
    with pytest.raises(OSError, match="disk full"):
        build.archive_onedir(directory, output)
    assert not output.exists()


def test_smoke_environment_removes_python_and_external_qt_paths(scripts, monkeypatch, tmp_path):
    _build, smoke = scripts
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    monkeypatch.setenv("PATH", r"C:\Python312;C:\venv\Scripts")
    monkeypatch.setenv("PYTHONPATH", "source")
    monkeypatch.setenv("PYTHONHOME", "interpreter")
    monkeypatch.setenv("QT_PLUGIN_PATH", "build-machine-qt")
    monkeypatch.setenv("QT_QPA_PLATFORM_PLUGIN_PATH", "build-machine-qt-platforms")
    monkeypatch.setenv("VIRTUAL_ENV", "venv")
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "old-freezer-extraction")
    environment = smoke.isolated_environment(tmp_path / "Roaming", tmp_path / "Local")
    assert environment["PATH"] == r"C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem"
    assert environment["QT_QPA_PLATFORM"] == "windows"
    assert environment["APPDATA"] == str(tmp_path / "Roaming")
    for variable in (
        "PYTHONPATH",
        "PYTHONHOME",
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "VIRTUAL_ENV",
        "_PYI_APPLICATION_HOME_DIR",
    ):
        assert variable not in environment


@pytest.mark.parametrize(
    "change,match",
    [
        ({"frozen": False}, "frozen"),
        ({"platform": "linux"}, "platform"),
        ({"qt_platform": "offscreen"}, "qt_platform"),
        ({"ui_constructed": False}, "ui_constructed"),
        ({"nvml_binding_available": False}, "nvml_binding_available"),
        ({"language_persistence": False}, "language_persistence"),
        ({"settings_roundtrip": False}, "settings_roundtrip"),
        ({"status": "failed"}, "status"),
        ({"errors": ["could not import psutil"]}, "reported errors"),
    ],
)
def test_smoke_rejects_invalid_or_source_mode_reports(scripts, tmp_path, change, match):
    _build, smoke = scripts
    report = report_fixture(tmp_path)
    report.update(change)
    with pytest.raises(RuntimeError, match=match):
        smoke.validate_report(report, tmp_path, second_run=False)


def test_smoke_rejects_missing_bilingual_executable_validation(scripts, tmp_path):
    _build, smoke = scripts
    report = report_fixture(tmp_path)
    report["languages_tested"] = ["ru"]
    with pytest.raises(RuntimeError, match="Russian and English"):
        smoke.validate_report(report, tmp_path, second_run=False)


def test_smoke_checks_settings_location_contents_and_relaunch(scripts, tmp_path):
    _build, smoke = scripts
    appdata = tmp_path / "Roaming"
    report = report_fixture(appdata)
    with pytest.raises(RuntimeError, match="survive relaunch"):
        smoke.validate_report(report, appdata, second_run=True)
    report["previous_settings"]["profile"] = "Eco"
    smoke.validate_report(report, appdata, second_run=True)
    original = report["settings_path"]
    report["settings_path"] = str(tmp_path / "_MEI1234" / "settings.json")
    with pytest.raises(RuntimeError, match="APPDATA"):
        smoke.validate_report(report, appdata, second_run=False)
    report["settings_path"] = original
    Path(report["persistence_probe_path"]).unlink()
    with pytest.raises(RuntimeError, match="persist"):
        smoke.validate_report(report, appdata, second_run=False)


def test_smoke_runs_exe_twice_from_isolated_directory_and_retains_reports(
    scripts, monkeypatch, tmp_path
):
    _build, smoke = scripts
    monkeypatch.setattr(smoke, "require_windows_x64", lambda: None)
    executable = tmp_path / "NEXUS-AI.exe"
    executable.write_bytes(b"explicit test fixture")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        appdata = Path(kwargs["env"]["APPDATA"])
        report = report_fixture(appdata, previous_profile="Eco" if len(calls) == 2 else "Smart")
        Path(command[-1]).write_text(json.dumps(report), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(smoke.subprocess, "run", run)
    reports = tmp_path / "reports"
    smoke.smoke_executable(executable, "onefile", reports)
    assert len(calls) == 2
    assert calls[0][1]["cwd"] == calls[1][1]["cwd"]
    assert calls[0][1]["cwd"] != executable.parent
    assert calls[0][1]["env"]["APPDATA"] == calls[1][1]["env"]["APPDATA"]
    assert calls[0][1]["timeout"] == 120
    assert calls[0][0][0] == str(executable.resolve())
    assert calls[0][0][1:3] == ["--self-test", "--self-test-report"]
    assert sorted(path.name for path in reports.iterdir()) == [
        "onefile-first.json",
        "onefile-first.log",
        "onefile-second.json",
        "onefile-second.log",
    ]


def test_smoke_nonzero_exit_is_failure_and_preserves_diagnostics(scripts, monkeypatch, tmp_path):
    _build, smoke = scripts
    monkeypatch.setattr(smoke, "require_windows_x64", lambda: None)
    executable = tmp_path / "NEXUS-AI.exe"
    executable.write_bytes(b"explicit test fixture")
    monkeypatch.setattr(
        smoke.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="", stderr="missing DLL"),
    )
    reports = tmp_path / "reports"
    with pytest.raises(RuntimeError, match="self-test failed"):
        smoke.smoke_executable(executable, "onedir", reports)
    assert "missing DLL" in (reports / "onedir-first.log").read_text(encoding="utf-8")
    assert not (reports / "onedir-second.log").exists()


def native_build_fixture(build, monkeypatch, tmp_path):
    monkeypatch.setattr(build, "require_windows_x64", lambda: None)
    monkeypatch.setattr(build.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(build, "_check_dependencies", lambda: None)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="0.3.0"\n', encoding="utf-8")
    (tmp_path / "README.md").write_text("Windows instructions", encoding="utf-8")


def emit_pyinstaller_fixture(command, **_kwargs):
    target = Path(command[command.index("--distpath") + 1])
    if "--onefile" in command:
        target.mkdir(parents=True)
        (target / "NEXUS-AI.exe").write_bytes(b"onefile fixture")
    else:
        make_onedir(target / "NEXUS-AI")


def test_failed_pyinstaller_build_does_not_smoke_or_leave_stale_zip(scripts, monkeypatch, tmp_path):
    build, _smoke = scripts
    native_build_fixture(build, monkeypatch, tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    portable = dist / "NEXUS-AI-Portable.zip"
    portable.write_bytes(b"stale artifact")
    standalone = dist / "NEXUS-AI.exe"
    standalone.write_bytes(b"stale standalone")
    (dist / "SHA256SUMS.txt").write_text("stale checksums", encoding="utf-8")
    smoke_calls = []
    monkeypatch.setattr(build, "smoke_executable", lambda *args: smoke_calls.append(args))

    def fail(command, **_kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(build.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        build.build("both", tmp_path)
    assert smoke_calls == []
    assert not portable.exists()
    assert not standalone.exists()
    assert not (dist / "SHA256SUMS.txt").exists()


def test_both_builds_must_pass_smoke_before_portable_zip_and_checksums(
    scripts, monkeypatch, tmp_path
):
    build, _smoke = scripts
    native_build_fixture(build, monkeypatch, tmp_path)
    smoke_calls = []

    def verify(executable, mode, reports_dir):
        assert executable.is_file()
        assert not (tmp_path / "dist" / "NEXUS-AI.exe").exists()
        assert not (tmp_path / "dist" / "NEXUS-AI-Portable.zip").exists()
        smoke_calls.append((mode, reports_dir))

    monkeypatch.setattr(build.subprocess, "run", emit_pyinstaller_fixture)
    monkeypatch.setattr(build, "smoke_executable", verify)
    artifacts = build.build("both", tmp_path)
    assert [mode for mode, _reports in smoke_calls] == ["onefile", "onedir"]
    assert [path.name for path in artifacts] == [
        "NEXUS-AI.exe",
        "NEXUS-AI-Portable.zip",
    ]
    assert artifacts[0] == tmp_path / "dist" / "NEXUS-AI.exe"
    assert (
        artifacts[0].read_bytes() == (tmp_path / "dist" / "onefile" / "NEXUS-AI.exe").read_bytes()
    )
    checksums = (tmp_path / "dist" / "SHA256SUMS.txt").read_text(encoding="utf-8")
    for artifact in artifacts:
        assert build._sha256(artifact) in checksums
    assert "  NEXUS-AI.exe\n" in checksums
    assert "  NEXUS-AI-Portable.zip\n" in checksums
    with zipfile.ZipFile(artifacts[1]) as archive:
        assert "NEXUS-AI/README.md" in archive.namelist()


def test_missing_build_dependencies_remove_stale_canonical_outputs(scripts, monkeypatch, tmp_path):
    build, _smoke = scripts
    native_build_fixture(build, monkeypatch, tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    for name in ("NEXUS-AI.exe", "NEXUS-AI-Portable.zip", "SHA256SUMS.txt"):
        (dist / name).write_bytes(b"stale artifact")

    def missing_dependencies():
        raise RuntimeError("Build dependencies are missing")

    monkeypatch.setattr(build, "_check_dependencies", missing_dependencies)
    with pytest.raises(RuntimeError, match="dependencies"):
        build.build("both", tmp_path)
    assert list(dist.iterdir()) == []


def test_late_smoke_failure_never_publishes_canonical_outputs(scripts, monkeypatch, tmp_path):
    build, _smoke = scripts
    native_build_fixture(build, monkeypatch, tmp_path)
    monkeypatch.setattr(build.subprocess, "run", emit_pyinstaller_fixture)
    verified_modes = []

    def verify(_executable, mode, _reports_dir):
        verified_modes.append(mode)
        if mode == "onedir":
            raise RuntimeError("onedir Qt launch failed")

    monkeypatch.setattr(build, "smoke_executable", verify)
    with pytest.raises(RuntimeError, match="Qt launch"):
        build.build("both", tmp_path)
    assert verified_modes == ["onefile", "onedir"]
    dist = tmp_path / "dist"
    for name in ("NEXUS-AI.exe", "NEXUS-AI-Portable.zip", "SHA256SUMS.txt"):
        assert not (dist / name).exists()
    assert (dist / "onefile" / "NEXUS-AI.exe").is_file()


def test_failed_zip_publication_removes_already_copied_root_exe(scripts, monkeypatch, tmp_path):
    build, _smoke = scripts
    native_build_fixture(build, monkeypatch, tmp_path)
    monkeypatch.setattr(build.subprocess, "run", emit_pyinstaller_fixture)
    monkeypatch.setattr(build, "smoke_executable", lambda *_args: None)

    def zip_failure(_directory, destination):
        assert (tmp_path / "dist" / "NEXUS-AI.exe").is_file()
        destination.write_bytes(b"incomplete zip")
        raise OSError("disk full")

    monkeypatch.setattr(build, "archive_onedir", zip_failure)
    with pytest.raises(OSError, match="disk full"):
        build.build("both", tmp_path)
    for name in ("NEXUS-AI.exe", "NEXUS-AI-Portable.zip", "SHA256SUMS.txt"):
        assert not (tmp_path / "dist" / name).exists()
