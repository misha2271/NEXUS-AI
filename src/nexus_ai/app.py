"""Application entry point; usable with ``python -m nexus_ai`` on Windows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from nexus_ai import __version__
from nexus_ai.settings import SettingsStore
from nexus_ai.ui.window import MainWindow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NEXUS AI desktop")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run a packaging probe without connecting to Ollama.",
    )
    parser.add_argument(
        "--self-test-report", type=Path, help="JSON output file for the packaging probe."
    )
    args = parser.parse_args(argv)
    if args.self_test != (args.self_test_report is not None):
        parser.error("Use --self-test and --self-test-report PATH together.")
    app = QApplication([sys.argv[0]])
    app.setApplicationName("NEXUS AI")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("NEXUS AI")
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#10151f"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#edf2f7"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#0b1019"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#182131"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#edf2f7"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#202b3f"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#edf2f7"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#4263eb"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    if args.self_test:
        from nexus_ai.diagnostics import run_self_test

        return run_self_test(app, args.self_test_report)
    window = MainWindow(SettingsStore())
    window.show()
    return app.exec()
