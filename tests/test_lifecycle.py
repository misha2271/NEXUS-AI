"""Ollama protocol and serialized resource-policy lifecycle, without a physical model."""

from __future__ import annotations

import json

import httpx
import pytest

from nexus_ai.gaming import GameDetection, GameProfile
from nexus_ai.lifecycle import LifecycleController
from nexus_ai.ollama import OllamaClient, OllamaError, OllamaModel


def game(name="Example", mode="Gaming", *, unload=True):
    return GameDetection(
        GameProfile(name, ("example.exe",), mode, unload), ("example.exe",), True, "found"
    )


def no_game(*, complete=True):
    return GameDetection(None, (), complete, "no match")


def test_game_transition_defers_owned_model_unload_and_restores_mode_without_eager_load():
    lifecycle = LifecycleController("Maximum AI")
    lifecycle.note_model_used("my-model:latest")
    lifecycle.set_busy(True)
    decision = lifecycle.observe(game())
    assert decision.mode == "Gaming" and decision.unload_model is None
    assert "deferred" in decision.status
    decision = lifecycle.set_busy(False)
    assert decision.unload_model == "my-model:latest"
    assert lifecycle.pending_operation == "my-model:latest"
    assert lifecycle.observe(game()).unload_model is None
    lifecycle.unloaded("my-model:latest")
    assert lifecycle.observe(game()).unload_model is None
    decision = lifecycle.observe(no_game())
    assert decision.mode == "Maximum AI" and decision.unload_model is None
    assert lifecycle.request_restore() == "Maximum AI"  # no network object is owned here


def test_unrelated_server_models_are_never_selected_for_automatic_unload():
    controller = LifecycleController()
    assert controller.observe(game()).unload_model is None
    controller.note_model_used("nexus-owned")
    assert controller.observe(game()).unload_model == "nexus-owned"


def test_access_denied_does_not_claim_a_game_exited():
    controller = LifecycleController("Eco")
    controller.observe(game())
    decision = controller.observe(no_game(complete=False))
    assert decision.game_name == "Example" and decision.mode == "Gaming"
    assert "incomplete" in decision.status
    assert controller.observe(no_game()).mode == "Eco"


def test_user_selected_base_mode_is_restored_when_the_game_exits():
    controller = LifecycleController("Smart")
    controller.observe(game())
    assert controller.set_base_mode("Eco").mode == "Gaming"
    assert controller.observe(no_game()).mode == "Eco"


def test_failed_unload_is_not_retried_on_each_detection_tick():
    controller = LifecycleController()
    controller.note_model_used("owned")
    assert controller.observe(game()).unload_model == "owned"
    controller.unload_failed("owned")
    for _ in range(3):
        assert controller.observe(game()).unload_model is None
    controller.note_model_used("owned")
    assert controller.observe(game()).unload_model == "owned"


def test_model_is_only_marked_unloaded_after_acknowledgement():
    controller = LifecycleController()
    controller.note_model_used("one")
    assert controller.observe(game()).unload_model == "one"
    controller.unloaded("unrelated")
    assert controller.pending_operation == "one"
    controller.unloaded("one")
    assert controller.pending_operation is None
    controller.note_model_used("two")
    assert controller.observe(game()).unload_model == "two"


def test_explicit_restore_is_not_immediately_undone_by_auto_unload():
    controller = LifecycleController()
    controller.note_model_used("one")
    assert controller.observe(game()).unload_model == "one"
    controller.unloaded("one")
    assert controller.request_restore() == "Gaming"
    controller.note_model_used("one")
    assert controller.observe(game()).unload_model is None
    controller.observe(no_game())
    assert controller.observe(game()).unload_model == "one"


def test_game_profile_can_leave_model_resident():
    controller = LifecycleController()
    controller.note_model_used("one")
    decision = controller.observe(game(mode="Smart", unload=False))
    assert decision.mode == "Smart" and decision.unload_model is None


def test_unload_uses_supported_api_not_delete_or_process_termination():
    calls = []

    def handle(request):
        calls.append(request)
        assert request.method == "POST" and request.url.path == "/ollama/api/generate"
        assert json.loads(request.content) == {
            "model": "tiny",
            "prompt": "",
            "stream": False,
            "keep_alive": 0,
        }
        return httpx.Response(
            200,
            json={"model": "tiny:latest", "response": "", "done": True, "done_reason": "unload"},
        )

    with OllamaClient("http://localhost/ollama", transport=httpx.MockTransport(handle)) as client:
        assert client.unload_model("tiny") is None
    assert len(calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "tiny", "response": "", "done": True},
        {"model": "wrong", "response": "", "done": True, "done_reason": "unload"},
        {"model": [], "response": "", "done": True, "done_reason": "unload"},
        {"model": "tiny", "response": "output", "done": True, "done_reason": "unload"},
        {"model": "tiny", "response": "", "done": 1, "done_reason": "unload"},
        {"model": "tiny", "response": "", "done": False, "done_reason": "unload"},
        [],
        {},
    ],
)
def test_unload_requires_real_completed_acknowledgement(payload):
    with OllamaClient(
        "http://localhost",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    ) as client:
        with pytest.raises(OllamaError):
            client.unload_model("tiny")


def test_explicit_load_is_empty_prompt_and_does_not_pull_downloads():
    def handle(request):
        assert request.url.path == "/api/generate"
        assert json.loads(request.content) == {
            "model": "tiny",
            "prompt": "",
            "stream": False,
            "keep_alive": "5m",
        }
        return httpx.Response(200, json={"model": "tiny", "response": "", "done": True})

    with OllamaClient("http://localhost", transport=httpx.MockTransport(handle)) as client:
        assert client.load_model("tiny") is None


@pytest.mark.parametrize(
    "retention", [0, -1, True, "-1", "0m", "forever", "25h", "5m; shell", None]
)
def test_warm_load_rejects_unbounded_or_invalid_retention_before_request(retention):
    with OllamaClient(
        "http://localhost", transport=httpx.MockTransport(lambda _: pytest.fail("unexpected I/O"))
    ) as client:
        with pytest.raises(ValueError):
            client.load_model("tiny", keep_alive=retention)


@pytest.mark.parametrize("model", [None, "", "tiny\n", "bad model", "x" * 513])
def test_invalid_lifecycle_model_never_reaches_server(model):
    with OllamaClient(
        "http://localhost", transport=httpx.MockTransport(lambda _: pytest.fail("unexpected I/O"))
    ) as client:
        with pytest.raises((ValueError, OllamaError)):
            client.unload_model(model)


def test_running_models_are_read_from_real_ps_protocol_and_sizes_validated():
    def handle(request):
        assert request.method == "GET" and request.url.path == "/api/ps"
        return httpx.Response(200, json={"models": [{"name": "tiny", "size": 4096}]})

    with OllamaClient("http://localhost", transport=httpx.MockTransport(handle)) as client:
        assert client.running_models() == [OllamaModel("tiny", 4096)]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"models": {}},
        {"models": [None]},
        {"models": [{"name": ""}]},
        {"models": [{"name": "x", "size": True}]},
    ],
)
def test_invalid_running_model_reports_fail_without_fake_loaded_status(payload):
    with OllamaClient(
        "http://localhost",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    ) as client:
        with pytest.raises(OllamaError):
            client.running_models()


def test_api_errors_do_not_claim_success():
    payload = {"error": "model not found"}
    with OllamaClient(
        "http://localhost",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    ) as client:
        with pytest.raises(OllamaError):
            client.unload_model("missing")
    with OllamaClient(
        "http://localhost", transport=httpx.MockTransport(lambda _: httpx.Response(503))
    ) as client:
        with pytest.raises(OllamaError, match="503"):
            client.load_model("tiny")
