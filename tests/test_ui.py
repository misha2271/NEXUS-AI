"""Exercise Qt signals and real background workers with isolated API fixtures."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import pytest
from PySide6.QtCore import QRunnable

from nexus_ai.ollama import OllamaError, OllamaModel
from nexus_ai.settings import SettingsStore
from nexus_ai.telemetry import GPUReading, TelemetrySnapshot
from nexus_ai.ui.window import MainWindow


@dataclass
class ApiFixture:
    models: list[OllamaModel] = field(
        default_factory=lambda: [OllamaModel("tiny:latest"), OllamaModel("other:latest")]
    )
    chunks: tuple[str, ...] = ("Hello ", "there!")
    discovery_error: str = ""
    chat_error: str = ""
    chat_calls: list[dict] = field(default_factory=list)
    worker_threads: list[int] = field(default_factory=list)
    closed: int = 0
    pause_after_chunk: bool = False
    stream_entered: threading.Event = field(default_factory=threading.Event)
    discovery_entered: threading.Event = field(default_factory=threading.Event)
    discovery_release: threading.Event | None = None

    def client(self, base_url):
        fixture = self

        class Client:
            def __enter__(self):
                fixture.worker_threads.append(threading.get_ident())
                return self

            def __exit__(self, *_):
                fixture.closed += 1

            def list_models(self):
                fixture.discovery_entered.set()
                if fixture.discovery_release is not None:
                    if not fixture.discovery_release.wait(5):
                        raise RuntimeError("Test did not release discovery worker")
                if fixture.discovery_error:
                    raise OllamaError(fixture.discovery_error)
                return fixture.models

            def stream_chat(self, model, messages, *, options, keep_alive, cancel_event):
                fixture.chat_calls.append(
                    {
                        "model": model,
                        "messages": [dict(message) for message in messages],
                        "options": dict(options),
                        "keep_alive": keep_alive,
                        "base_url": base_url,
                    }
                )
                fixture.stream_entered.set()
                for text in fixture.chunks:
                    yield text
                    if fixture.pause_after_chunk:
                        if not cancel_event.wait(5):
                            raise RuntimeError("Test did not cancel paused stream")
                        return
                if fixture.chat_error:
                    raise OllamaError(fixture.chat_error)

        return Client()


@pytest.fixture
def make_window(qtbot, tmp_path):
    windows = []
    fixtures = []

    def create(api=None, *, settings=None, store=None):
        api = api or ApiFixture()
        store = store or SettingsStore(tmp_path / f"settings-{len(windows)}.json")
        if settings is not None:
            store.save(settings)
        window = MainWindow(store, client_factory=api.client, start_background=False)
        windows.append(window)
        fixtures.append(api)
        qtbot.addWidget(window)
        window.show()
        return window, api

    yield create
    for api in fixtures:
        if api.discovery_release is not None:
            api.discovery_release.set()
    for window in windows:
        window.close()
        qtbot.waitUntil(
            lambda window=window: (
                not window._jobs
                and not window._pool.activeThreadCount()
                and (window._monitor_thread is None or not window._monitor_thread.isRunning())
                and not window.isVisible()
            ),
            timeout=7000,
        )


def finish_jobs(qtbot, window):
    qtbot.waitUntil(lambda: not window._jobs and not window._pool.activeThreadCount(), timeout=5000)


def discover(qtbot, window):
    window.refresh_models()
    finish_jobs(qtbot, window)


def test_discovery_enables_send_only_with_model_and_text(make_window, qtbot):
    window, api = make_window()
    window.prompt.setPlainText("Hello")
    assert not window.send_button.isEnabled()
    discover(qtbot, window)
    assert window.model_combo.count() == 2
    assert window.model_combo.currentData() == "tiny:latest"
    assert "2 installed" in window.connection_status.text()
    assert window.send_button.isEnabled()
    window.prompt.setPlainText("  \n")
    assert not window.send_button.isEnabled()
    assert api.worker_threads and all(t != threading.get_ident() for t in api.worker_threads)
    assert api.closed == 1


def test_streamed_replies_preserve_context_and_apply_profile(make_window, qtbot):
    window, api = make_window()
    discover(qtbot, window)
    window.profile_combo.setCurrentText("Eco")
    window.prompt.setPlainText("First question")
    window.send_message()
    finish_jobs(qtbot, window)
    assert "Hello there!" in window.transcript.toPlainText()
    assert window._messages == [
        {"role": "user", "content": "First question"},
        {"role": "assistant", "content": "Hello there!"},
    ]
    assert api.chat_calls[0]["options"]["num_gpu"] == 0
    assert api.chat_calls[0]["options"]["num_thread"] == 1
    assert api.chat_calls[0]["keep_alive"] == 0
    assert window.connection_status.text() == "Ready · reply complete"
    window.prompt.setPlainText("Follow-up")
    window.send_message()
    finish_jobs(qtbot, window)
    assert api.chat_calls[1]["messages"] == [
        {"role": "user", "content": "First question"},
        {"role": "assistant", "content": "Hello there!"},
        {"role": "user", "content": "Follow-up"},
    ]
    assert api.closed == 3


def test_failed_partial_reply_restores_prompt_and_excludes_context(make_window, qtbot):
    api = ApiFixture(chunks=("partial",), chat_error="Ollama disconnected")
    window, _ = make_window(api)
    discover(qtbot, window)
    window.prompt.setPlainText("Try this")
    window.send_message()
    finish_jobs(qtbot, window)
    assert window.prompt.toPlainText() == "Try this"
    assert window._messages == []
    assert "Reply failed: Ollama disconnected" in window.transcript.toPlainText()
    assert window.send_button.isEnabled()
    assert window.refresh_button.isEnabled()
    assert not window.stop_button.isEnabled()


def test_failure_preserves_new_draft_typed_during_generation(make_window, qtbot):
    api = ApiFixture(chunks=(), chat_error="Unavailable")
    window, _ = make_window(api)
    discover(qtbot, window)
    window.prompt.setPlainText("Original question")
    window.send_message()
    # Worker signals are queued until the Qt event loop runs again.
    window.prompt.setPlainText("Next question already drafted")
    finish_jobs(qtbot, window)
    assert window.prompt.toPlainText() == "Next question already drafted"
    assert window._messages == []


def test_empty_model_list_explains_manual_install_and_blocks_send(make_window, qtbot):
    window, _ = make_window(ApiFixture(models=[]))
    window.prompt.setPlainText("Hello")
    discover(qtbot, window)
    assert "ollama pull" in window.connection_status.text()
    assert not window.send_button.isEnabled()
    assert window.refresh_button.isEnabled()
    assert window.settings_button.isEnabled()


def test_offline_discovery_is_recoverable(make_window, qtbot):
    api = ApiFixture(discovery_error="Cannot reach Ollama; run ollama serve")
    window, _ = make_window(api)
    window.prompt.setPlainText("Hello")
    discover(qtbot, window)
    assert "ollama serve" in window.connection_status.text()
    assert not window.send_button.isEnabled()
    assert window.refresh_button.isEnabled()
    api.discovery_error = ""
    discover(qtbot, window)
    assert window.send_button.isEnabled()


def test_profile_and_explicit_model_selection_persist(make_window, qtbot, tmp_path):
    store = SettingsStore(tmp_path / "persisted.json")
    window, _ = make_window(store=store)
    discover(qtbot, window)
    window.profile_combo.setCurrentText("Gaming")
    window.model_combo.setCurrentIndex(1)
    persisted = store.load()
    assert persisted.profile == "Gaming"
    assert persisted.model == "other:latest"
    restored, _ = make_window(store=store)
    discover(qtbot, restored)
    assert restored.profile_combo.currentText() == "Gaming"
    assert restored.model_combo.currentData() == "other:latest"


def test_cancel_excludes_partial_reply_and_releases_safe_controls(make_window, qtbot):
    api = ApiFixture(chunks=("partial reply",), pause_after_chunk=True)
    window, _ = make_window(api)
    discover(qtbot, window)
    window.prompt.setPlainText("Question to cancel")
    window.send_message()
    qtbot.waitUntil(lambda: "partial reply" in window.transcript.toPlainText())
    assert not window.refresh_button.isEnabled()
    assert not window.settings_button.isEnabled()
    assert not window.model_combo.isEnabled()
    assert not window.clear_button.isEnabled()
    assert window.stop_button.isEnabled()
    window.stop_generation()
    assert not window.stop_button.isEnabled()
    finish_jobs(qtbot, window)
    assert window._messages == []
    assert "partial reply excluded from context" in window.transcript.toPlainText()
    assert window.refresh_button.isEnabled()
    assert window.model_combo.isEnabled()
    assert not window.stop_button.isEnabled()
    api.pause_after_chunk = False
    api.chunks = ("new answer",)
    window.prompt.setPlainText("New question")
    window.send_message()
    finish_jobs(qtbot, window)
    assert api.chat_calls[-1]["messages"] == [{"role": "user", "content": "New question"}]


def test_empty_successful_reply_does_not_enter_history(make_window, qtbot):
    window, _ = make_window(ApiFixture(chunks=()))
    discover(qtbot, window)
    window.prompt.setPlainText("Question")
    window.send_message()
    finish_jobs(qtbot, window)
    assert window._messages == []
    assert "No answer text" in window.connection_status.text()


def test_cancel_before_worker_starts_does_not_leave_stopping_status(make_window, qtbot):
    entered = threading.Event()
    release = threading.Event()

    class BlockingJob(QRunnable):
        def run(self):
            entered.set()
            release.wait(5)

    window, api = make_window()
    discover(qtbot, window)
    window._pool.setMaxThreadCount(1)
    window._pool.start(BlockingJob())
    try:
        qtbot.waitUntil(entered.is_set)
        window.prompt.setPlainText("Cancel before start")
        window.send_message()
        window.stop_generation()
    finally:
        release.set()
    finish_jobs(qtbot, window)
    assert api.chat_calls == []
    assert window._messages == []
    assert window.connection_status.text() == "Stopped. Ready for another message."
    assert window.refresh_button.isEnabled()


def unavailable_snapshot(**changes):
    values = {
        "cpu_percent": None,
        "ram_percent": None,
        "ram_used_bytes": None,
        "ram_total_bytes": None,
        "ram_available_bytes": None,
        "gpus": (),
        "gpu_status": "NVIDIA driver unavailable",
        "cpu_status": "CPU telemetry unavailable",
        "ram_status": "RAM telemetry unavailable",
    }
    values.update(changes)
    return TelemetrySnapshot(**values)


def test_missing_telemetry_is_not_rendered_as_zero(make_window):
    window, _ = make_window()
    window._show_telemetry(unavailable_snapshot())
    assert window.cpu_card.value.text() == "CPU telemetry unavailable"
    assert window.ram_card.value.text() == "RAM telemetry unavailable"
    assert window.cpu_card.bar.isHidden()
    assert window.ram_card.bar.isHidden()
    assert window.gpu_status.text() == "NVIDIA driver unavailable"
    assert window._gpu_cards == {}
    window._show_telemetry(
        unavailable_snapshot(gpus=(GPUReading(0, "GPU", None, None, None, None),))
    )
    card = window._gpu_cards[0]
    assert "Utilization unavailable" in card.value.text()
    assert "Temperature unavailable" in card.value.text()
    assert "VRAM: Unavailable / Unavailable" in card.value.text()
    assert card.bar.isHidden()
    window._telemetry_failed("Hardware disconnected")
    assert window._snapshot is None
    assert window._gpu_cards == {}
    assert "Hardware disconnected" in window.gpu_status.text()
    window._show_telemetry(unavailable_snapshot())
    assert window._gpu_cards == {}


def test_close_waits_for_discovery_worker_without_blocking_ui(make_window, qtbot):
    release = threading.Event()
    api = ApiFixture(discovery_release=release)
    window, _ = make_window(api)
    window.refresh_models()
    qtbot.waitUntil(api.discovery_entered.is_set)
    window.close()
    assert window.isVisible()
    assert window._closing
    assert not window.settings_button.isEnabled()
    assert not window.profile_combo.isEnabled()
    assert not window.prompt.isEnabled()
    assert "Closing" in window.connection_status.text()
    release.set()
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=5000)
    assert not window._jobs
    assert not window._pool.activeThreadCount()
    assert api.closed == 1


def test_monitor_runs_off_ui_thread_and_closes_collector(make_window, qtbot):
    sampled = threading.Event()
    closed = threading.Event()
    threads = []

    class Collector:
        def sample(self):
            threads.append(threading.get_ident())
            sampled.set()
            return unavailable_snapshot(cpu_percent=37.5)

        def close(self):
            threads.append(threading.get_ident())
            closed.set()

    window, _ = make_window()
    window._start_monitor(Collector)
    qtbot.waitUntil(lambda: sampled.is_set() and window.cpu_card.value.text() == "37.5%")
    assert not window.cpu_card.bar.isHidden()
    assert window.cpu_card.bar.value() == 38
    window.close()
    qtbot.waitUntil(lambda: closed.is_set() and not window.isVisible(), timeout=5000)
    assert not window._monitor_thread.isRunning()
    assert threads and all(thread != threading.get_ident() for thread in threads)
