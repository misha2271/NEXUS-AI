"""Capture the real Qt UI and live host telemetry, without injected sample data.

Run with QT_QPA_PLATFORM=offscreen on a headless host. Ollama discovery uses the
normal configured default endpoint; an absent server is shown as unavailable.
The temporary preferences never change the user's saved settings.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from nexus_ai.settings import Settings, SettingsStore
from nexus_ai.ui.window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/screenshots"))
    parser.add_argument("--language", choices=("ru", "en"), default="ru")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyle("Fusion")
    failures: list[str] = []
    captured: list[str] = []
    with tempfile.TemporaryDirectory(prefix="nexus-ui-capture-") as temporary:
        store = SettingsStore(Path(temporary) / "settings.json")
        store.save(Settings(language=args.language))
        window = MainWindow(store)
        window.resize(1440, 1150)
        window.show()

        def capture() -> None:
            try:
                for name, route, size in (
                    ("overview.png", "overview", (1440, 1150)),
                    ("assistant.png", "assistant", (1280, 860)),
                    ("rgb-unavailable.png", "rgb", (1280, 860)),
                    ("game-center.png", "gaming", (1280, 1000)),
                    ("ssd-health.png", "ssd", (1280, 1000)),
                    ("gamepad-lab.png", "gamepad", (1280, 1000)),
                    ("update-center.png", "updates", (1440, 1000)),
                    ("compact.png", "overview", (780, 900)),
                ):
                    window.navigate(route)
                    window.resize(*size)
                    app.processEvents()
                    if not window.grab().save(str(args.output / name)):
                        raise RuntimeError(f"Could not save {name}")
                    captured.append(name)

                def capture_settings() -> None:
                    dialog = QApplication.activeModalWidget()
                    try:
                        app.processEvents()
                        if not dialog.grab().save(str(args.output / "settings.png")):
                            raise RuntimeError("Could not save Settings screenshot")
                        captured.append("settings.png")
                    except Exception as exc:
                        failures.append(str(exc))
                    finally:
                        dialog.reject()

                QTimer.singleShot(0, capture_settings)
                window.open_settings()
                print(f"Captured {len(window.history.points)} actual host samples.")
                print("Ollama status:", window.connection_status.text())
                print("GPU status:", window.gpu_status.text())
                print("Temperature status:", window.temperature_status.text())
            except Exception as exc:
                failures.append(str(exc))
            finally:
                window.close()  # drains real workers through the normal asynchronous close path

        QTimer.singleShot(12000, capture)
        app.exec()
    if failures or len(captured) != 9:
        raise RuntimeError("Screenshot capture incomplete: " + "; ".join(failures))
    print("Saved:", ", ".join(captured))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
