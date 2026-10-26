"""Pure, thread-independent messages. English sources are stable gettext-style keys.

Services retain structured messages instead of selecting a global locale. The UI
renders them in its current language, including messages received before a switch.
User prompts, model answers, identifiers and external diagnostics remain raw data.
"""

from __future__ import annotations

from string import Formatter
from typing import Iterable

from nexus_ai.translations import RU

LANGUAGES = ("ru", "en")


class Text(str):
    def __new__(cls, source: str, **values):
        instance = super().__new__(cls, source.format(**values))
        instance.source = source
        instance.values = values
        return instance

    def __getnewargs_ex__(self):
        return (self.source,), self.values

    def render(self, language: str) -> str:
        template = RU.get(self.source, self.source) if language == "ru" else self.source
        return _Formatter(language).vformat(template, (), self.values)


class JoinedText(str):
    def __new__(cls, parts: Iterable[str], separator: str = "\n"):
        parts = tuple(parts)
        instance = super().__new__(cls, separator.join(parts))
        instance.parts = parts
        instance.separator = separator
        return instance

    def __getnewargs_ex__(self):
        return (self.parts, self.separator), {}

    def render(self, language: str) -> str:
        return self.separator.join(render(part, language) for part in self.parts)


class _Formatter(Formatter):
    def __init__(self, language: str):
        self.language = language

    def format_field(self, value, format_spec):
        if isinstance(value, (Text, JoinedText)):
            return format(value.render(self.language), format_spec)
        result = super().format_field(value, format_spec)
        if self.language == "ru" and isinstance(value, float):
            result = result.replace(".", ",")
        return result


def render(message: str, language: str) -> str:
    if language not in LANGUAGES:
        raise ValueError("Unsupported language")
    if isinstance(message, (Text, JoinedText)):
        return message.render(language)
    return RU.get(message, message) if language == "ru" else message


def error_text(error: object) -> str:
    if isinstance(error, BaseException):
        if error.args and isinstance(error.args[0], (Text, JoinedText)):
            return error.args[0]
        return str(error) or type(error).__name__
    return error if isinstance(error, str) else str(error)
