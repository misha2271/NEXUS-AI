"""Explicit STT/TTS contracts and an allowlisted Russian/English text router.

No microphone, wake-word listener, speech engine or speaker is initialized here.
Audio operations require an explicitly supplied, available, validated provider;
recognizing a known text command does not establish an audio capability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from threading import Event
from typing import Protocol

from nexus_ai.i18n import LANGUAGES, Text


class VoiceError(Exception):
    """A safe provider/capability/input failure, not an invented transcript."""


@dataclass(frozen=True)
class VoiceAvailability:
    available: bool = False
    validated: bool = False
    reason: str = "No validated speech provider is connected."
    languages: frozenset[str] = frozenset()

    def permits(self, language: str) -> bool:
        return (
            self.available is True
            and self.validated is True
            and isinstance(self.languages, frozenset)
            and language in LANGUAGES
            and language in self.languages
        )


class SpeechRecognizer(Protocol):
    """Implementations own decoding; callers must run them on a worker thread."""

    def status(self) -> VoiceAvailability: ...

    def transcribe(self, audio: bytes, *, language: str, cancel_event: Event) -> str: ...


class SpeechSynthesizer(Protocol):
    """Implementations own playback; no OS voice is assumed to exist."""

    def status(self) -> VoiceAvailability: ...

    def speak(self, text: str, *, language: str, cancel_event: Event) -> None: ...


@dataclass(frozen=True)
class VoiceIntent:
    command: str
    profile: str | None = None


_RUSSIAN = {
    "стоп": VoiceIntent("stop_generation"),
    "останови ответ": VoiceIntent("stop_generation"),
    "остановить ответ": VoiceIntent("stop_generation"),
    "прекрати ответ": VoiceIntent("stop_generation"),
    "статус": VoiceIntent("status"),
    "состояние системы": VoiceIntent("status"),
    "покажи статус": VoiceIntent("status"),
    "игровой режим": VoiceIntent("set_profile", "Gaming"),
    "режим игры": VoiceIntent("set_profile", "Gaming"),
    "включи игровой режим": VoiceIntent("set_profile", "Gaming"),
    "умный режим": VoiceIntent("set_profile", "Smart"),
    "включи умный режим": VoiceIntent("set_profile", "Smart"),
    "максимум ии": VoiceIntent("set_profile", "Maximum AI"),
    "режим максимум ии": VoiceIntent("set_profile", "Maximum AI"),
    "включи максимум ии": VoiceIntent("set_profile", "Maximum AI"),
    "эко режим": VoiceIntent("set_profile", "Eco"),
    "режим эко": VoiceIntent("set_profile", "Eco"),
    "экономичный режим": VoiceIntent("set_profile", "Eco"),
    "включи экономичный режим": VoiceIntent("set_profile", "Eco"),
}
_ENGLISH = {
    "stop": VoiceIntent("stop_generation"),
    "stop generation": VoiceIntent("stop_generation"),
    "cancel reply": VoiceIntent("stop_generation"),
    "status": VoiceIntent("status"),
    "system status": VoiceIntent("status"),
    "show status": VoiceIntent("status"),
    "gaming mode": VoiceIntent("set_profile", "Gaming"),
    "switch to gaming": VoiceIntent("set_profile", "Gaming"),
    "smart mode": VoiceIntent("set_profile", "Smart"),
    "switch to smart": VoiceIntent("set_profile", "Smart"),
    "maximum ai mode": VoiceIntent("set_profile", "Maximum AI"),
    "switch to maximum ai": VoiceIntent("set_profile", "Maximum AI"),
    "eco mode": VoiceIntent("set_profile", "Eco"),
    "switch to eco": VoiceIntent("set_profile", "Eco"),
}


def parse_voice_intent(text: str, language: str = "ru") -> VoiceIntent | None:
    """Match a complete approved phrase, never infer or execute arbitrary commands."""
    if language not in LANGUAGES:
        raise VoiceError(Text("Choose Russian or English."))
    if (
        not isinstance(text, str)
        or len(text) > 256
        or any(ord(character) < 32 and character not in "\t\r\n" for character in text)
    ):
        return None
    normalized = re.sub(r"\s+", " ", text.strip().casefold().replace("ё", "е"))
    normalized = re.sub(r"^(?:nexus|нексус)[, ]+", "", normalized)
    normalized = normalized.rstrip(".!?").strip()
    return (_RUSSIAN if language == "ru" else _ENGLISH).get(normalized)


class VoiceFoundation:
    """Default-deny provider orchestration; no built-in audio backend is shipped."""

    def __init__(
        self,
        recognizer: SpeechRecognizer | None = None,
        synthesizer: SpeechSynthesizer | None = None,
    ) -> None:
        self.recognizer = recognizer
        self.synthesizer = synthesizer

    @staticmethod
    def _status(provider) -> VoiceAvailability:
        if provider is None:
            return VoiceAvailability(reason=Text("No validated speech provider is connected."))
        try:
            status = provider.status()
        except Exception as exc:
            return VoiceAvailability(
                reason=Text(
                    "Speech provider check failed: {error}",
                    error=str(exc) or type(exc).__name__,
                )
            )
        if (
            not isinstance(status, VoiceAvailability)
            or type(status.available) is not bool
            or type(status.validated) is not bool
            or not isinstance(status.reason, str)
            or not isinstance(status.languages, frozenset)
            or not status.languages.issubset(LANGUAGES)
        ):
            return VoiceAvailability(
                reason=Text("The speech provider returned invalid capabilities.")
            )
        return status

    def recognition_status(self) -> VoiceAvailability:
        return self._status(self.recognizer)

    def synthesis_status(self) -> VoiceAvailability:
        return self._status(self.synthesizer)

    def status(self, language: str = "ru") -> VoiceAvailability:
        if language not in LANGUAGES:
            raise VoiceError(Text("Choose Russian or English."))
        recognition, synthesis = self.recognition_status(), self.synthesis_status()
        if not recognition.permits(language) or not synthesis.permits(language):
            return VoiceAvailability(
                reason=Text(
                    "Voice assistance is unavailable without validated recognition "
                    "and speech providers."
                )
            )
        return VoiceAvailability(
            available=True,
            validated=True,
            reason=Text(
                "Explicit speech providers are connected; no automatic recording is enabled."
            ),
            languages=recognition.languages & synthesis.languages,
        )

    def transcribe(
        self,
        audio: bytes,
        *,
        language: str = "ru",
        cancel_event: Event | None = None,
    ) -> str:
        if language not in LANGUAGES:
            raise VoiceError(Text("Choose Russian or English."))
        if not isinstance(audio, bytes) or not audio or len(audio) > 10 * 1024 * 1024:
            raise VoiceError(
                Text("Speech input must be nonempty audio bytes within the size limit.")
            )
        if self.recognizer is None or not self.recognition_status().permits(language):
            raise VoiceError(Text("Speech recognition is unavailable for this language."))
        cancellation = cancel_event if cancel_event is not None else Event()
        if cancellation.is_set():
            raise VoiceError(Text("The speech operation was cancelled."))
        try:
            result = self.recognizer.transcribe(audio, language=language, cancel_event=cancellation)
        except Exception as exc:
            raise VoiceError(
                Text(
                    "Speech recognition failed: {error}",
                    error=str(exc) or type(exc).__name__,
                )
            ) from exc
        if cancellation.is_set():
            raise VoiceError(Text("The speech operation was cancelled."))
        if not isinstance(result, str) or len(result) > 65_536:
            raise VoiceError(Text("The speech provider returned an invalid transcript."))
        try:
            result.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise VoiceError(Text("The speech provider returned an invalid transcript.")) from exc
        return result

    def speak(
        self,
        text: str,
        *,
        language: str = "ru",
        cancel_event: Event | None = None,
    ) -> None:
        if language not in LANGUAGES:
            raise VoiceError(Text("Choose Russian or English."))
        if not isinstance(text, str) or not text.strip() or len(text) > 4096:
            raise VoiceError(Text("Speech output must be nonempty text within the size limit."))
        try:
            text.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise VoiceError(Text("Speech output must contain valid Unicode text.")) from exc
        if self.synthesizer is None or not self.synthesis_status().permits(language):
            raise VoiceError(Text("Speech playback is unavailable for this language."))
        cancellation = cancel_event if cancel_event is not None else Event()
        if cancellation.is_set():
            raise VoiceError(Text("The speech operation was cancelled."))
        try:
            self.synthesizer.speak(text, language=language, cancel_event=cancellation)
        except Exception as exc:
            raise VoiceError(
                Text(
                    "Speech playback failed: {error}",
                    error=str(exc) or type(exc).__name__,
                )
            ) from exc
        if cancellation.is_set():
            raise VoiceError(Text("The speech operation was cancelled."))
