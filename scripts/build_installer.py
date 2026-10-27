"""Compile and exercise the actual per-user Windows installer with Inno Setup.

Run after scripts/build_windows.py --mode both on native Windows x64.
The compiler must be installed separately; this script never downloads tools.
It refuses to smoke-install over a user's existing NEXUS installation.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path

from build_windows import validate_onedir
from smoke_windows import require_windows_x64, smoke_executable

APP_ID = "NEXUS-AI-Desktop"


def find_compiler(explicit: Path | None = None) -> Path:
    if explicit is not None:
        if not explicit.is_file():
            raise RuntimeError("The supplied Inno Setup compiler path does not exist.")
        return explicit.resolve()
    candidates = []
    executable = shutil.which("ISCC.exe")
    if executable:
        candidates.append(Path(executable))
    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        directory = os.environ.get(variable)
        if directory:
            candidates.extend(
                Path(directory) / f"Inno Setup {version}" / "ISCC.exe" for version in (6, 7)
            )
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("Inno Setup ISCC.exe was not found. Install Inno Setup or use --iscc.")


def existing_installation() -> bool:
    """Protect an existing per-user install from the build-machine smoke test."""
    import winreg

    key = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}_is1"
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ | view):
                return True
        except FileNotFoundError:
            continue
    return False


def smoke_installer(installer: Path, reports: Path, *, cleanup_timeout: float = 10) -> None:
    """Install, launch the installed EXE twice, and uninstall without elevation."""
    reports.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nexus-installer-smoke-") as temporary:
        installed = Path(temporary) / "NEXUS AI"
        uninstaller = installed / "unins000.exe"
        try:
            subprocess.run(
                [
                    str(installer),
                    "/VERYSILENT",
                    "/SUPPRESSMSGBOXES",
                    "/NORESTART",
                    "/SP-",
                    "/NOICONS",
                    "/LANG=russian",
                    f"/DIR={installed}",
                    f"/LOG={reports / 'installer-install.log'}",
                ],
                check=True,
                timeout=180,
            )
            validate_onedir(installed)
            if not uninstaller.is_file():
                raise RuntimeError("The installer did not create its uninstaller.")
            smoke_executable(installed / "NEXUS-AI.exe", "installed", reports)
        finally:
            if uninstaller.is_file():
                subprocess.run(
                    [
                        str(uninstaller),
                        "/VERYSILENT",
                        "/SUPPRESSMSGBOXES",
                        "/NORESTART",
                        f"/LOG={reports / 'installer-uninstall.log'}",
                    ],
                    check=True,
                    timeout=180,
                )
        deadline = time.monotonic() + cleanup_timeout
        while (installed / "NEXUS-AI.exe").exists() or (installed / "_internal").exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("Silent uninstall left installed application files behind.")
            time.sleep(0.1)
        if existing_installation():
            raise RuntimeError("Silent uninstall left its per-user uninstall registration behind.")


def _checksums(dist: Path, installer: Path | None = None) -> None:
    files = [dist / "NEXUS-AI.exe", dist / "NEXUS-AI-Portable.zip"]
    if installer is not None:
        files.append(installer)
    entries = []
    for file in files:
        if file.is_file():
            with file.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            entries.append(f"{digest}  {file.name}\n")
    temporary = dist / "SHA256SUMS.txt.tmp"
    temporary.write_text("".join(entries), encoding="utf-8")
    temporary.replace(dist / "SHA256SUMS.txt")


def build(root: Path, *, iscc: Path | None = None) -> Path:
    require_windows_x64()
    root = root.resolve()
    compiler = find_compiler(iscc)
    version = tomllib.loads((root / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise RuntimeError("The installer requires a stable three-part application version.")
    if existing_installation():
        raise RuntimeError(
            "Use a clean build account: NEXUS AI is already installed for this user."
        )
    source = root / "dist" / "onedir" / "NEXUS-AI"
    validate_onedir(source)
    reports = root / "dist" / "smoke"
    reports.mkdir(parents=True, exist_ok=True)
    destination = root / "dist" / f"NEXUS-AI-Setup-{version}.exe"
    destination.unlink(missing_ok=True)
    _checksums(root / "dist")
    try:
        smoke_executable(source / "NEXUS-AI.exe", "installer-source", reports)
        with tempfile.TemporaryDirectory(prefix="installer-compile-", dir=root / "dist") as scratch:
            subprocess.run(
                [
                    str(compiler),
                    "/Qp",
                    f"/DAppVersion={version}",
                    f"/DSourceDir={source}",
                    f"/DOutputDir={scratch}",
                    str(root / "packaging" / "windows" / "nexus.iss"),
                ],
                cwd=root,
                check=True,
                timeout=300,
            )
            compiled = Path(scratch) / destination.name
            if not compiled.is_file():
                raise RuntimeError("Inno Setup did not create the expected installer.")
            smoke_installer(compiled, reports)
            shutil.copy2(compiled, destination)
        _checksums(root / "dist", destination)
    except Exception:
        destination.unlink(missing_ok=True)
        _checksums(root / "dist")
        raise
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iscc", type=Path)
    args = parser.parse_args(argv)
    try:
        installer = build(Path(__file__).resolve().parents[1], iscc=args.iscc)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Installer build failed: {exc}\n")
    print(f"Native installer build, installation, launch and uninstall passed: {installer}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
