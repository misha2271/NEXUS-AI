"""Small synchronous Ollama client intended to run in background workers.

The API is deliberately independent of Qt. Cancellation is checked between stream
chunks; an in-flight network read is bounded by the configured read timeout.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from threading import Event
from typing import Any, Iterator

import httpx


class OllamaError(Exception):
    """An actionable connection, HTTP, or Ollama protocol error."""


@dataclass(frozen=True)
class OllamaModel:
    name: str
    size_bytes: int | None = None


class OllamaClient:
    """Use an existing Ollama server; never installs or downloads anything."""

    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: httpx.Timeout | float | None = None,
    ) -> None:
        try:
            url = httpx.URL(base_url.strip())
        except (httpx.InvalidURL, AttributeError) as exc:
            raise ValueError("Ollama URL must be an HTTP or HTTPS URL.") from exc
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "Ollama URL needs an HTTP(S) host without credentials, query, or fragment."
            )
        self.base_url = str(url).rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url + "/",
            timeout=timeout
            if timeout is not None
            else httpx.Timeout(connect=5, read=60, write=15, pool=5),
            transport=transport,
        )

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def list_models(self) -> list[OllamaModel]:
        """Return the server's installed models from ``GET /api/tags``."""
        try:
            response = self._client.get("api/tags")
            self._check_status(response)
            payload = self._decode_object(response.text)
        except httpx.RequestError as exc:
            raise self._network_error(exc) from exc
        if "error" in payload:
            raise OllamaError(f"Ollama: {payload['error']}")
        models = payload.get("models")
        if not isinstance(models, list):
            raise OllamaError("Ollama returned an invalid model list (expected 'models').")
        result: list[OllamaModel] = []
        for item in models:
            if not isinstance(item, dict):
                raise OllamaError("Ollama returned an invalid model entry.")
            name = item.get("name")
            size = item.get("size")
            if not isinstance(name, str) or not name.strip():
                raise OllamaError("Ollama returned a model without a valid name.")
            if size is not None and (type(size) is not int or size < 0):
                raise OllamaError("Ollama returned an invalid model size.")
            result.append(OllamaModel(name=name, size_bytes=size))
        return result

    def stream_chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        options: dict[str, Any] | None = None,
        keep_alive: str | int = "5m",
        cancel_event: Event | None = None,
    ) -> Iterator[str]:
        """Yield assistant text from Ollama's newline-delimited JSON stream.

        Network and protocol failures raise :class:`OllamaError`, including a
        stream that ends without its final ``done`` marker. Cancelling returns
        normally and closes the response. A blocked read can take up to 60 s
        with the default timeout, including the initial model load.
        """
        if not isinstance(model, str) or not model.strip():
            raise OllamaError("Select an installed model before sending a message.")
        if self._cancelled(cancel_event):
            return
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": keep_alive,
            "options": options or {},
        }
        try:
            with self._client.stream("POST", "api/chat", json=body) as response:
                if not response.is_success:
                    response.read()
                    self._check_status(response, model=model)
                for line in response.iter_lines():
                    if self._cancelled(cancel_event):
                        return
                    if not line.strip():
                        continue
                    chunk = self._decode_object(line)
                    if "error" in chunk:
                        raise OllamaError(self._server_error(chunk["error"], model))
                    done = chunk.get("done", False)
                    if not isinstance(done, bool):
                        raise OllamaError("Ollama returned an invalid 'done' marker.")
                    message = chunk.get("message")
                    if message is not None:
                        if not isinstance(message, dict):
                            raise OllamaError("Ollama returned an invalid chat message.")
                        # Thinking-capable models may send a reasoning-only
                        # message before their answer. Do not display reasoning
                        # as the assistant's answer or require answer text yet.
                        if "content" not in message and isinstance(message.get("thinking"), str):
                            content = ""
                        else:
                            content = message.get("content")
                        if not isinstance(content, str):
                            raise OllamaError("Ollama returned an invalid chat message.")
                        if content:
                            yield content
                    elif not done:
                        raise OllamaError("Ollama returned a chat chunk without a message.")
                    if done:
                        return
                if self._cancelled(cancel_event):
                    return
                raise OllamaError("Ollama disconnected before completing the reply. Try again.")
        except httpx.RequestError as exc:
            if self._cancelled(cancel_event):
                return
            raise self._network_error(exc) from exc

    @staticmethod
    def _cancelled(event: Event | None) -> bool:
        return event is not None and event.is_set()

    @staticmethod
    def _decode_object(text: str) -> dict[str, Any]:
        try:
            payload = json.loads(text)
        except (ValueError, TypeError) as exc:
            raise OllamaError("Ollama returned malformed JSON. Check the server URL.") from exc
        if not isinstance(payload, dict):
            raise OllamaError("Ollama returned an invalid response (expected a JSON object).")
        return payload

    @classmethod
    def _check_status(cls, response: httpx.Response, model: str | None = None) -> None:
        if response.is_success:
            return
        detail = ""
        try:
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("error"), str):
                detail = payload["error"]
        except (ValueError, UnicodeError):
            pass
        if model is not None and response.status_code == 404:
            raise OllamaError(
                f"Model '{model}' is unavailable. Install it with 'ollama pull {model}', "
                "then refresh the model list. " + detail
            )
        error = f"Ollama HTTP {response.status_code}."
        if detail:
            error += " " + detail
        if response.status_code == 404:
            error += " Check the server URL; it must point to an Ollama server."
        raise OllamaError(error)

    @staticmethod
    def _network_error(exc: httpx.RequestError) -> OllamaError:
        if isinstance(exc, httpx.TimeoutException):
            return OllamaError(
                "Ollama request timed out. The model may still be loading; "
                "check Ollama and try again, or choose a smaller model."
            )
        return OllamaError(
            "Cannot reach Ollama. Start it with 'ollama serve' and check the server URL."
        )

    @staticmethod
    def _server_error(error: object, model: str) -> str:
        detail = error if isinstance(error, str) else "Unknown server error"
        message = f"Ollama: {detail}"
        if "not found" in detail.lower():
            message += f" Install the model with 'ollama pull {model}' and refresh models."
        return message
