"""Create native Windows x64 PyInstaller builds and validate their actual EXEs.

Run with the project's Windows virtual-environment Python after installing the
``freeze`` and ``nvidia`` extras. This script intentionally rejects Linux and
does not attempt Windows cross-compilation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from smoke_windows import require_windows_x64, smoke_executable

MODES = ("onefile", "onedir")


def pyinstaller_command(root: Path, mode: str) -> list[str]:
    """Explicit build configuration; PyInstaller writes its generated spec under build/."""
    if mode not in MODES:
        raise ValueError(f"Unsupported build mode: {mode}")
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--noupx",
        "--windowed",
        f"--{mode}",
        "--name",
        "NEXUS-AI",
        "--distpath",
        str(root / "dist" / mode),
        "--workpath",
        str(root / "build" / "pyinstaller" / mode),
        "--specpath",
        str(root / "build" / "spec" / mode),
        "--paths",
        str(root / "src"),
    ]
    # PyInstaller's PySide6 hooks collect the imported Qt libraries and platform
    # plugins. These explicit imports also document the only Qt modules we use.
    for module in (
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "psutil._psutil_windows",
        "pynvml",  # Loaded with importlib by the optional hardware backend.
        "sqlite3",
        "ssl",
        "http.server",
        "ctypes",
    ):
        command.extend(("--hidden-import", module))
    command.extend(("--collect-data", "certifi"))
    if mode == "onedir":
        command.extend(("--contents-directory", "_internal"))
    command.append(str(root / "packaging" / "windows" / "entrypoint.py"))
    return command


def validate_onedir(directory: Path) -> None:
    if not (directory / "NEXUS-AI.exe").is_file():
        raise RuntimeError("PyInstaller onedir output is missing NEXUS-AI.exe.")
    internal = directory / "_internal"
    if not internal.is_dir():
        raise RuntimeError("PyInstaller onedir output is missing its _internal dependencies.")
    if not any(path.parent.name == "platforms" for path in internal.rglob("qwindows.dll")):
        raise RuntimeError("PySide6's Windows platform plugin qwindows.dll was not bundled.")


def archive_onedir(directory: Path, destination: Path) -> None:
    """Keep the complete PyInstaller directory together under one ZIP root."""
    validate_onedir(directory)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for source in sorted(directory.rglob("*")):
                if source.is_file():
                    archive.write(source, source.relative_to(directory.parent))
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _check_dependencies() -> None:
    missing = [
        module
        for module in ("PyInstaller", "PySide6", "psutil", "pynvml", "httpx", "certifi")
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        raise RuntimeError(
            "Build dependencies are missing: "
            + ", ".join(missing)
            + '. Install with: python -m pip install -e ".[freeze,nvidia]"'
        )


def _sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def build(mode: str, root: Path) -> list[Path]:
    require_windows_x64()
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("Use native Windows x64, not ARM or a cross-compilation environment.")
    if mode not in (*MODES, "both"):
        raise ValueError(f"Unsupported build mode: {mode}")
    root = root.resolve()
    dist = root / "dist"
    standalone = dist / "NEXUS-AI.exe"
    portable = dist / "NEXUS-AI-Portable.zip"
    checksums = dist / "SHA256SUMS.txt"
    checksums.unlink(missing_ok=True)
    if mode in {"both", "onefile"}:
        standalone.unlink(missing_ok=True)
    if mode in {"both", "onedir"}:
        portable.unlink(missing_ok=True)
    _check_dependencies()
    dist.mkdir(parents=True, exist_ok=True)
    selected_modes = MODES if mode == "both" else (mode,)
    reports_dir = dist / "smoke"
    for selected in selected_modes:
        for previous in reports_dir.glob(f"{selected}-*"):
            if previous.is_file():
                previous.unlink()
        target = dist / selected
        if target.exists():
            shutil.rmtree(target)
    verified: dict[str, Path] = {}
    artifacts: list[Path] = []
    try:
        for selected in selected_modes:
            target = dist / selected
            subprocess.run(pyinstaller_command(root, selected), cwd=root, check=True)
            executable = target / "NEXUS-AI.exe"
            if selected == "onedir":
                executable = target / "NEXUS-AI" / "NEXUS-AI.exe"
                validate_onedir(executable.parent)
            if not executable.is_file():
                raise RuntimeError(f"PyInstaller did not create its executable: {executable}")
            smoke_executable(executable, selected, reports_dir)
            verified[selected] = executable
        # Publish the canonical download names only after all requested launches
        # pass. The mode directories remain available for direct diagnostics.
        if "onefile" in verified:
            shutil.copy2(verified["onefile"], standalone)
            artifacts.append(standalone)
        if "onedir" in verified:
            directory = verified["onedir"].parent
            shutil.copy2(root / "README.md", directory / "README.md")
            archive_onedir(directory, portable)
            artifacts.append(portable)
        checksums.write_text(
            "".join(
                f"{_sha256(path)}  {path.relative_to(dist).as_posix()}\n" for path in artifacts
            ),
            encoding="utf-8",
        )
    except Exception:
        if "onefile" in selected_modes:
            standalone.unlink(missing_ok=True)
        if "onedir" in selected_modes:
            portable.unlink(missing_ok=True)
        checksums.unlink(missing_ok=True)
        raise
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=(*MODES, "both"), default="both")
    args = parser.parse_args(argv)
    try:
        artifacts = build(args.mode, Path(__file__).resolve().parents[1])
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Windows build failed: {exc}\n")
    print("Native Windows build and standalone launch validation succeeded:")
    for artifact in artifacts:
        print(artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
