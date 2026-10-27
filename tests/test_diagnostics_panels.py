"""Real Qt worker boundaries, cancellation and integrity-driven UI permissions."""

import hashlib
import threading
from pathlib import Path
from types import SimpleNamespace

from nexus_ai.gamepad import GamepadReport
from nexus_ai.i18n import Text
from nexus_ai.storage import StorageReport
from nexus_ai.ui.diagnostics_panels import GamepadPanel, StoragePanel, UpdatePanel
from nexus_ai.ui.localization import Translator
from nexus_ai.updates import Release, ReleaseAsset, StagedUpdate, UpdateCheck, Version


def wait_idle(qtbot, panel):
    qtbot.waitUntil(lambda: not panel.busy, timeout=5000)


def test_storage_scan_is_off_ui_thread_and_language_state_is_preserved(qtbot):
    main = threading.get_ident()
    threads = []

    class Collector:
        def collect(self):
            threads.append(threading.get_ident())
            return StorageReport(
                False, (), Text("Windows Storage diagnostics are unavailable on this platform.")
            )

    panel = StoragePanel(Translator("en"), collector_factory=Collector)
    qtbot.addWidget(panel)
    panel.scan()
    wait_idle(qtbot, panel)
    assert threads and threads[0] != main
    assert "unavailable" in panel.status.text()
    assert "not estimates" in panel.output.toPlainText()
    panel.shutdown()
    panel.scan()
    assert not panel.busy and not panel.scan_button.isEnabled()


def test_gamepad_panel_does_not_invent_controller_on_empty_snapshot(qtbot):
    class Collector:
        def collect(self):
            return GamepadReport(
                True, (), Text("XInput returned {count} connected controller(s).", count=0)
            )

    panel = GamepadPanel(Translator("en"), collector_factory=Collector)
    qtbot.addWidget(panel)
    panel.scan()
    wait_idle(qtbot, panel)
    assert "0 connected" in panel.status.text()
    assert "Slot" not in panel.output.toPlainText()
    assert "not supported" in panel.output.toPlainText()
    panel.shutdown()


def checked(*, digest=True, major=False):
    version = Version(2 if major else 1, 1, 0)
    asset = ReleaseAsset(
        "NEXUS.exe",
        "https://github.com/misha2271/NEXUS-AI/releases/download/v1.1.0/NEXUS.exe",
        1,
        hashlib.sha256(b"x").hexdigest() if digest else None,
    )
    release = Release(
        "v1.1.0", version, "https://github.com/misha2271/NEXUS-AI/releases/tag/v1.1.0", (asset,)
    )
    return UpdateCheck("available", Text("New release"), Version(1, 0, 0), release)


def test_unverified_asset_stays_disabled(qtbot, tmp_path):
    panel = UpdatePanel(Translator("en"), "1.0.0", tmp_path)
    qtbot.addWidget(panel)
    panel._result(checked(digest=False))
    assert not panel.download_button.isEnabled()
    assert panel.assets.count() == 0
    assert not panel.install_button.isEnabled()
    assert "download disabled" in panel.output.toPlainText()
    panel.shutdown()


def test_check_is_off_ui_thread_and_uses_current_version(qtbot, tmp_path):
    calls = []
    main = threading.get_ident()

    class Checker:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def check(self, version):
            calls.append((threading.get_ident(), version))
            return checked()

    panel = UpdatePanel(Translator("en"), "1.0.0", tmp_path, checker_factory=Checker)
    qtbot.addWidget(panel)
    panel.scan()
    wait_idle(qtbot, panel)
    assert calls and calls[0][0] != main and calls[0][1] == "1.0.0"
    assert panel.assets.count() == 1 and panel.download_button.isEnabled()
    assert not panel.install_button.isEnabled()
    panel.shutdown()


def test_major_download_requires_second_approval_and_never_installs(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    calls = []
    answers = iter([QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No])
    monkeypatch.setattr(QMessageBox, "question", lambda *_: next(answers))

    class Checker:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def stage_asset(self, *args, **kwargs):
            calls.append((args, kwargs))
            return StagedUpdate(Path(tmp_path) / "file.exe", "a" * 64, "v2.1.0")

    panel = UpdatePanel(Translator("en"), "1.0.0", tmp_path, checker_factory=Checker)
    qtbot.addWidget(panel)
    panel._result(checked(major=True))
    panel.download()
    assert calls == [] and not panel.busy
    answers = iter([QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.Yes])
    panel.download()
    wait_idle(qtbot, panel)
    assert calls and calls[0][0][3].major_approved
    assert not panel.install_button.isEnabled()
    assert "Nothing was installed" in panel.status.text()
    panel.shutdown()


def test_cancel_does_not_wait_for_running_collection_or_deliver_stale_result(qtbot):
    started, release = threading.Event(), threading.Event()

    class Collector:
        def collect(self):
            started.set()
            release.wait(3)
            return SimpleNamespace(message=Text("late result"), disks=())

    panel = StoragePanel(Translator("en"), collector_factory=Collector)
    qtbot.addWidget(panel)
    panel.scan()
    qtbot.waitUntil(started.is_set)
    panel.shutdown()
    assert panel.busy
    release.set()
    wait_idle(qtbot, panel)
    assert "late result" not in panel.status.text()


def test_update_actions_reflow_for_russian_compact_layout(qtbot, tmp_path):
    panel = UpdatePanel(Translator("ru"), "1.0.0", tmp_path)
    qtbot.addWidget(panel)
    panel.assets.addItem("NEXUS-AI-1.0.0-Windows-x86_64-portable-with-a-long-filename.zip")
    panel.resize(410, 720)
    panel.show()
    qtbot.waitUntil(lambda: panel.action_grid.columns == 1)
    assert panel.width() == 410
    for widget in (
        panel.scan_button,
        panel.assets,
        panel.download_button,
        panel.cancel_button,
        panel.install_button,
    ):
        assert widget.geometry().right() <= panel.action_grid.width()
        assert widget.width() <= panel.action_grid.width()
    panel.resize(760, 720)
    qtbot.waitUntil(lambda: panel.action_grid.columns == 2)
    panel.i18n.set_language("en")
    assert panel.scan_button.text() == "Check GitHub Releases"
    panel.shutdown()


def test_update_shutdown_during_check_does_not_wait_or_show_late_release(qtbot, tmp_path):
    from PySide6.QtCore import QTimer

    started, release = threading.Event(), threading.Event()
    event_loop_ticks = []

    class Checker:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def check(self, version):
            started.set()
            release.wait(3)
            return checked()

    panel = UpdatePanel(Translator("en"), "1.0.0", tmp_path, checker_factory=Checker)
    qtbot.addWidget(panel)
    panel.scan()
    qtbot.waitUntil(started.is_set)
    panel.shutdown()
    assert panel.busy
    QTimer.singleShot(0, lambda: event_loop_ticks.append(True))
    qtbot.waitUntil(lambda: bool(event_loop_ticks))
    assert panel.busy and not panel.scan_button.isEnabled()
    assert not panel.download_button.isEnabled()
    release.set()
    wait_idle(qtbot, panel)
    assert panel._check is None and panel.assets.count() == 0
    assert not panel.scan_button.isEnabled() and not panel.install_button.isEnabled()
