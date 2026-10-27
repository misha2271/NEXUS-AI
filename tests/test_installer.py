"""Installer orchestration fixtures do not pretend to compile Windows binaries."""

from __future__ import annotations

import hashlib
import importlib
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def installer(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("build_installer")


def mock_onedir(directory):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "NEXUS-AI.exe").write_bytes(b"unit-test fixture; not a real executable")
    plugin = directory / "_internal" / "PySide6" / "plugins" / "platforms" / "qwindows.dll"
    plugin.parent.mkdir(parents=True)
    plugin.write_bytes(b"unit-test fixture")


def build_fixture(installer, monkeypatch, tmp_path):
    monkeypatch.setattr(installer, "require_windows_x64", lambda: None)
    monkeypatch.setattr(installer, "existing_installation", lambda: False)
    compiler = tmp_path / "ISCC.exe"
    compiler.write_bytes(b"explicit mocked compiler")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="1.0.0"\n', "utf-8")
    dist = tmp_path / "dist"
    mock_onedir(dist / "onedir" / "NEXUS-AI")
    (dist / "NEXUS-AI.exe").write_bytes(b"mock standalone")
    (dist / "NEXUS-AI-Portable.zip").write_bytes(b"mock portable")
    return compiler, dist


def test_installer_refuses_linux_before_compiler_registry_and_files(
    installer, monkeypatch, tmp_path
):
    calls = []

    def refuse():
        raise RuntimeError("native Windows required")

    monkeypatch.setattr(installer, "require_windows_x64", refuse)
    monkeypatch.setattr(installer, "find_compiler", lambda _value: calls.append("compiler"))
    with pytest.raises(RuntimeError, match="native Windows"):
        installer.build(tmp_path)
    assert not calls
    assert list(tmp_path.iterdir()) == []


def test_existing_user_installation_is_never_touched(installer, monkeypatch, tmp_path):
    compiler, _dist = build_fixture(installer, monkeypatch, tmp_path)
    monkeypatch.setattr(installer, "existing_installation", lambda: True)
    calls = []
    monkeypatch.setattr(installer.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(RuntimeError, match="already installed"):
        installer.build(tmp_path, iscc=compiler)
    assert not calls


def test_success_publishes_installer_and_matching_checksums_only_after_smoke(
    installer, monkeypatch, tmp_path
):
    compiler, dist = build_fixture(installer, monkeypatch, tmp_path)
    events = []
    destination = dist / "NEXUS-AI-Setup-1.0.0.exe"

    def compile_setup(command, **kwargs):
        events.append("compile")
        assert kwargs["check"] is True and kwargs["timeout"] == 300
        assert command[0] == str(compiler)
        assert "/DAppVersion=1.0.0" in command
        output = Path(
            next(
                arg.removeprefix("/DOutputDir=")
                for arg in command
                if arg.startswith("/DOutputDir=")
            )
        )
        (output / destination.name).write_bytes(b"mock compiled installer; not an EXE")

    def smoke_setup(file, _reports):
        events.append("installed smoke")
        assert file.is_file() and not destination.exists()

    monkeypatch.setattr(installer, "smoke_executable", lambda *_args: events.append("source smoke"))
    monkeypatch.setattr(installer, "smoke_installer", smoke_setup)
    monkeypatch.setattr(installer.subprocess, "run", compile_setup)
    assert installer.build(tmp_path, iscc=compiler) == destination
    assert events == ["source smoke", "compile", "installed smoke"]
    checksums = (dist / "SHA256SUMS.txt").read_text("utf-8").splitlines()
    assert len(checksums) == 3
    for line in checksums:
        digest, filename = line.split("  ")
        assert digest == hashlib.sha256((dist / filename).read_bytes()).hexdigest()


@pytest.mark.parametrize("stage", ["compile", "installed smoke"])
def test_failed_installer_never_leaves_a_download_or_checksum(
    installer, monkeypatch, tmp_path, stage
):
    compiler, dist = build_fixture(installer, monkeypatch, tmp_path)
    destination = dist / "NEXUS-AI-Setup-1.0.0.exe"
    destination.write_bytes(b"old unvalidated installer")
    (dist / "SHA256SUMS.txt").write_text("stale installer checksum", "utf-8")
    monkeypatch.setattr(installer, "smoke_executable", lambda *_args: None)

    def compile_setup(command, **_kwargs):
        if stage == "compile":
            raise subprocess.CalledProcessError(1, command)
        output = Path(
            next(
                arg.removeprefix("/DOutputDir=")
                for arg in command
                if arg.startswith("/DOutputDir=")
            )
        )
        (output / destination.name).write_bytes(b"mock installer")

    def fail_smoke(*_args):
        raise RuntimeError("installed EXE could not launch")

    monkeypatch.setattr(installer.subprocess, "run", compile_setup)
    monkeypatch.setattr(installer, "smoke_installer", fail_smoke)
    with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
        installer.build(tmp_path, iscc=compiler)
    assert not destination.exists()
    checksums = (dist / "SHA256SUMS.txt").read_text("utf-8")
    assert "Setup" not in checksums and "stale" not in checksums
    assert "NEXUS-AI.exe" in checksums and "NEXUS-AI-Portable.zip" in checksums


def test_silent_install_launch_and_uninstall_preserve_separation(installer, monkeypatch, tmp_path):
    commands = []
    launched = []
    installed = None

    def run(command, **kwargs):
        nonlocal installed
        commands.append(command)
        assert kwargs["check"] is True and kwargs["timeout"] == 180
        if command[0] == "mock-setup.exe":
            installed = Path(
                next(arg.removeprefix("/DIR=") for arg in command if arg.startswith("/DIR="))
            )
            mock_onedir(installed)
            (installed / "unins000.exe").write_bytes(b"mock uninstaller")
        else:
            assert command[0] == str(installed / "unins000.exe")
            shutil.rmtree(installed)

    monkeypatch.setattr(installer.subprocess, "run", run)
    monkeypatch.setattr(installer, "existing_installation", lambda: False)
    monkeypatch.setattr(installer, "smoke_executable", lambda *args: launched.append(args))
    installer.smoke_installer(Path("mock-setup.exe"), tmp_path / "reports")
    assert launched[0][0] == installed / "NEXUS-AI.exe"
    assert launched[0][1] == "installed"
    assert len(commands) == 2
    assert "/VERYSILENT" in commands[0] and "/NOICONS" in commands[0]
    assert "/VERYSILENT" in commands[1]


def test_missing_installed_payload_fails_even_when_setup_returns_zero(
    installer, monkeypatch, tmp_path
):
    monkeypatch.setattr(installer.subprocess, "run", lambda *_args, **_kwargs: None)
    with pytest.raises(RuntimeError, match="missing NEXUS-AI.exe"):
        installer.smoke_installer(Path("mock-setup.exe"), tmp_path / "reports")
