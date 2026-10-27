"""Voice foundation tests deliberately do not claim physical audio validation."""

from __future__ import annotations

from threading import Event

import pytest

from nexus_ai.voice import VoiceAvailability, VoiceError, VoiceFoundation, parse_voice_intent


@pytest.mark.parametrize(
    "phrase,command,profile",
    [
        ("Нексус, останови ответ!", "stop_generation", None),
        (" СТАТУС ", "status", None),
        ("покажи статус", "status", None),
        ("включи игровой режим", "set_profile", "Gaming"),
        ("умный режим", "set_profile", "Smart"),
        ("режим максимум ИИ", "set_profile", "Maximum AI"),
        ("экономичный режим", "set_profile", "Eco"),
    ],
)
def test_russian_commands_match_only_known_intents(phrase, command, profile):
    intent = parse_voice_intent(phrase)
    assert (intent.command, intent.profile) == (command, profile)


@pytest.mark.parametrize(
    "phrase,profile",
    [
        ("NEXUS, switch to gaming.", "Gaming"),
        ("smart mode", "Smart"),
        ("maximum ai mode", "Maximum AI"),
        ("switch to eco", "Eco"),
    ],
)
def test_english_profiles_keep_canonical_ids(phrase, profile):
    assert parse_voice_intent(phrase, "en").profile == profile


@pytest.mark.parametrize(
    "phrase",
    [
        "удали файлы",
        "обнови прошивку",
        "включи вентилятор",
        "запусти powershell",
        "игровой режим и удали файлы",
        "стоп; calc.exe",
        "стоп\x00",
        "A" * 257,
        "stop",
        None,
        42,
    ],
)
def test_unknown_or_compound_russian_commands_never_execute(phrase):
    assert parse_voice_intent(phrase) is None


def test_no_providers_means_no_claimed_recording_recognition_or_playback():
    voice = VoiceFoundation()
    assert not voice.status().available and not voice.status().validated
    assert not voice.recognition_status().available
    assert not voice.synthesis_status().available
    with pytest.raises(VoiceError, match="recognition is unavailable"):
        voice.transcribe(b"actual supplied audio")
    with pytest.raises(VoiceError, match="playback is unavailable"):
        voice.speak("Привет")


class ExplicitTestProvider:
    """An explicitly injected test double, not a shipped or physically verified SDK."""

    def __init__(self, status=None):
        self.availability = status or VoiceAvailability(
            True, True, "explicit test fixture", frozenset({"ru"})
        )
        self.calls = []

    def status(self):
        return self.availability

    def transcribe(self, audio, *, language, cancel_event):
        self.calls.append(("transcribe", audio, language, cancel_event))
        return "Исходная фраза {без изменений}"

    def speak(self, text, *, language, cancel_event):
        self.calls.append(("speak", text, language, cancel_event))


def test_explicit_validated_provider_contracts_preserve_data_and_cancellation_event():
    provider = ExplicitTestProvider()
    voice = VoiceFoundation(provider, provider)
    event = Event()
    assert voice.status().permits("ru")
    assert not voice.status().permits("en")
    assert voice.transcribe(b"bytes", cancel_event=event) == "Исходная фраза {без изменений}"
    voice.speak("Original {text}", cancel_event=event)
    assert provider.calls[0][1:] == (b"bytes", "ru", event)
    assert provider.calls[1][1:] == ("Original {text}", "ru", event)
    with pytest.raises(VoiceError, match="unavailable"):
        voice.speak("English", language="en")


@pytest.mark.parametrize("available,validated", [(True, False), (False, True), (False, False)])
def test_available_alone_or_validated_alone_does_not_authorize_audio(available, validated):
    provider = ExplicitTestProvider(
        VoiceAvailability(available, validated, "not usable", frozenset({"ru"}))
    )
    voice = VoiceFoundation(provider, provider)
    assert not voice.status().available
    with pytest.raises(VoiceError):
        voice.transcribe(b"audio")
    with pytest.raises(VoiceError):
        voice.speak("text")
    assert provider.calls == []


def test_cancel_before_and_after_provider_operation_does_not_return_fake_text():
    provider = ExplicitTestProvider()
    event = Event()
    event.set()
    voice = VoiceFoundation(provider, provider)
    with pytest.raises(VoiceError, match="cancelled"):
        voice.transcribe(b"audio", cancel_event=event)
    assert provider.calls == []
    event.clear()

    def cancelled(audio, **_kwargs):
        event.set()
        return "must not escape"

    provider.transcribe = cancelled
    with pytest.raises(VoiceError, match="cancelled"):
        voice.transcribe(b"audio", cancel_event=event)


@pytest.mark.parametrize(
    "audio",
    [b"", "not audio bytes", b"a" * (10 * 1024 * 1024 + 1)],
    ids=["empty", "wrong-type", "over-10-mib"],
)
def test_audio_input_limits_are_enforced_before_calling_provider(audio):
    provider = ExplicitTestProvider()
    with pytest.raises(VoiceError, match="size limit"):
        VoiceFoundation(provider).transcribe(audio)
    assert provider.calls == []


def test_broken_or_invalid_provider_status_remains_unavailable():
    provider = ExplicitTestProvider()

    def failed():
        raise RuntimeError("SDK not loaded")

    provider.status = failed
    assert not VoiceFoundation(provider, provider).status().available
    assert "SDK not loaded" in VoiceFoundation(provider).recognition_status().reason
    provider.status = lambda: {"available": True, "validated": True}
    assert not VoiceFoundation(provider).recognition_status().available


def test_failed_or_invalid_transcription_is_an_error_not_an_invented_transcript():
    provider = ExplicitTestProvider()

    def failed(*_args, **_kwargs):
        raise OSError("actual backend failure")

    provider.transcribe = failed
    with pytest.raises(VoiceError, match="actual backend failure"):
        VoiceFoundation(provider).transcribe(b"audio")
    provider.transcribe = lambda *_args, **_kwargs: None
    with pytest.raises(VoiceError, match="invalid transcript"):
        VoiceFoundation(provider).transcribe(b"audio")


def test_unknown_language_is_rejected_instead_of_selecting_another_voice():
    with pytest.raises(VoiceError, match="Russian or English"):
        VoiceFoundation().status("de")
    with pytest.raises(VoiceError, match="Russian or English"):
        parse_voice_intent("стоп", "de")


def test_truthy_nonboolean_capabilities_do_not_unlock_audio():
    provider = ExplicitTestProvider(
        VoiceAvailability("yes", "yes", "invalid capability types", frozenset({"ru"}))
    )
    voice = VoiceFoundation(provider, provider)
    assert not voice.recognition_status().available
    assert not voice.status().available
    with pytest.raises(VoiceError):
        voice.transcribe(b"audio")
    assert provider.calls == []


def test_unknown_provider_language_and_invalid_unicode_are_rejected():
    provider = ExplicitTestProvider(
        VoiceAvailability(True, True, "unknown language", frozenset({"de"}))
    )
    assert not VoiceFoundation(provider).recognition_status().available
    provider = ExplicitTestProvider()
    provider.transcribe = lambda *_args, **_kwargs: "\ud800"
    with pytest.raises(VoiceError, match="invalid transcript"):
        VoiceFoundation(provider).transcribe(b"audio")
    with pytest.raises(VoiceError, match="valid Unicode"):
        VoiceFoundation(synthesizer=provider).speak("\ud800")
