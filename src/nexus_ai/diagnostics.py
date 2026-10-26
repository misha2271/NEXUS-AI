"""An explicit packaging probe for the native executable, independent of Ollama.

Results go to a file because a windowed PyInstaller executable has no console.
The settings probe is separate from the user's real settings.json. Running it
twice checks persistence across separate processes and onefile extraction dirs.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import math
import platform
import sys
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import qVersion
from PySide6.QtWidgets import QApplication

from nexus_ai import __version__
from nexus_ai.settings import Settings, SettingsStore
from nexus_ai.telemetry import TelemetryCollector
from nexus_ai.ui.window import MainWindow


def run_self_test(app: QApplication, report_path: Path) -> int:
    """Exercise bundled Qt, psutil, optional NVML, and persistent preferences.

    No chat requests or model downloads occur. Unsupported NVIDIA hardware is a
    valid result. Failures return nonzero and are written to the JSON report.
    """
    report: dict[str, object] = {
        "status": "failed",
        "errors": [],
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "platform": sys.platform,
        "python_version": platform.python_version(),
        "executable": sys.executable,
        "qt_version": qVersion(),
        "qt_platform": app.platformName(),
        "ui_constructed": False,
        "settings_roundtrip": False,
        "nvml_binding_available": False,
    }
    window: MainWindow | None = None
    collector: TelemetryCollector | None = None
    errors: list[str] = []
    try:
        real_store = SettingsStore()
        probe = SettingsStore(real_store.path.with_name(".packaging-self-test.json"))
        report["settings_path"] = str(real_store.path)
        report["persistence_probe_path"] = str(probe.path)
        report["previous_settings"] = asdict(probe.load())
        expected = Settings(profile="Eco")
        probe.save(expected)
        restored = probe.load()
        if restored != expected or probe.warning:
            raise RuntimeError("Settings could not be restored from the packaging probe.")
        report["settings_roundtrip"] = True
        if importlib.util.find_spec("pynvml") is not None:
            importlib.import_module("pynvml")
            report["nvml_binding_available"] = True

        window = MainWindow(probe, start_background=False)
        window.show()
        app.processEvents()
        if not window.isVisible() or window.profile_combo.currentText() != expected.profile:
            raise RuntimeError("The Qt desktop window did not initialize correctly.")
        report["ui_constructed"] = True

        collector = TelemetryCollector()
        collector.sample()  # Prime psutil's per-thread CPU interval counter.
        snapshot = collector.sample()
        report["telemetry"] = asdict(snapshot)
        if snapshot.ram_total_bytes is None or snapshot.ram_total_bytes <= 0:
            raise RuntimeError("Bundled psutil could not read physical memory.")
        if (
            snapshot.cpu_percent is None
            or not math.isfinite(snapshot.cpu_percent)
            or not 0 <= snapshot.cpu_percent <= 100
        ):
            raise RuntimeError("Bundled psutil could not read CPU utilization.")
        if (
            snapshot.ram_percent is None
            or not math.isfinite(snapshot.ram_percent)
            or not 0 <= snapshot.ram_percent <= 100
            or snapshot.ram_used_bytes is None
            or not 0 <= snapshot.ram_used_bytes <= snapshot.ram_total_bytes
            or snapshot.ram_available_bytes is None
            or not 0 <= snapshot.ram_available_bytes <= snapshot.ram_total_bytes
        ):
            raise RuntimeError("Bundled psutil returned invalid memory telemetry.")
        window._show_telemetry(snapshot)
        app.processEvents()
        if report["frozen"] and sys.platform == "win32":
            screenshot_path = Path(report_path).with_suffix(".png")
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(screenshot_path)):
                raise RuntimeError("The frozen UI screenshot could not be saved.")
            report["screenshot_path"] = str(screenshot_path)
    except Exception as exc:
        errors.append(str(exc) or type(exc).__name__)
    finally:
        if collector is not None:
            try:
                collector.close()
            except Exception as exc:
                errors.append(f"Telemetry cleanup failed: {exc}")
        if window is not None:
            try:
                window.close()
                window.deleteLater()
                app.processEvents()
            except Exception as exc:
                errors.append(f"Window cleanup failed: {exc}")

    report["errors"] = errors
    report["status"] = "failed" if errors else "passed"
    try:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return 1
    return 1 if errors else 0
