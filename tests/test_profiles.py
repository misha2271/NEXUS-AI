import pytest

from nexus_ai.profiles import PROFILE_NAMES, resolve_policy


def test_all_profiles_produce_real_bounded_ollama_budgets():
    for name in PROFILE_NAMES:
        policy = resolve_policy(name, cpu_count=8, ram_available_bytes=16 * 1024**3)
        assert 1 <= policy.options["num_thread"] <= 8
        assert policy.options["num_ctx"] >= 2048
        assert policy.monitor_interval_ms >= 1000
        assert policy.description


def test_smart_reduces_budget_under_cpu_pressure():
    normal = resolve_policy("Smart", cpu_count=16, cpu_percent=25)
    busy = resolve_policy("Smart", cpu_count=16, cpu_percent=90)
    assert busy.options["num_thread"] < normal.options["num_thread"]
    assert busy.options["num_ctx"] < normal.options["num_ctx"]


def test_smart_low_ram_unloads_model():
    policy = resolve_policy("Smart", cpu_count=8, ram_available_bytes=2 * 1024**3)
    assert policy.keep_alive == 0
    assert policy.options["num_ctx"] == 2048


@pytest.mark.parametrize("name", ["Gaming", "Eco"])
def test_background_profiles_request_cpu_only_and_unload(name):
    policy = resolve_policy(name, cpu_count=16)
    assert policy.options["num_gpu"] == 0
    assert policy.options["num_thread"] <= 2
    assert policy.keep_alive == 0


def test_maximum_ai_increases_budget_without_forcing_gpu():
    smart = resolve_policy("Smart", cpu_count=16)
    maximum = resolve_policy("Maximum AI", cpu_count=16)
    assert maximum.options["num_thread"] > smart.options["num_thread"]
    assert maximum.options["num_ctx"] > smart.options["num_ctx"]
    assert "num_gpu" not in maximum.options


@pytest.mark.parametrize("profile", PROFILE_NAMES)
def test_single_cpu_budgets_remain_valid(profile):
    assert resolve_policy(profile, cpu_count=1).options["num_thread"] == 1


def test_unknown_profile_rejected():
    with pytest.raises(ValueError):
        resolve_policy("Turbo")
