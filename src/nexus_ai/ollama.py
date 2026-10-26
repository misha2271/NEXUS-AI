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

from nexus_ai.i18n import JoinedText, Text


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
            raise ValueError(Text("Ollama URL must be an HTTP or HTTPS URL.")) from exc
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                Text("Ollama URL needs an HTTP(S) host without credentials, query, or fragment.")
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

    def unload_model(self, model: str) -> None:
        """Ask Ollama to unload one explicitly selected model.

        Ollama is a shared server: unloading can affect another application
        using the same model. Call only after user opt-in, from a worker,
        and never while a NEXUS chat request is active.
        """
        if not isinstance(model, str) or not model.strip():
            raise OllamaError(Text("Select an installed model before sending a message."))
        model = model.strip()
        try:
            response = self._client.post(
                "api/generate",
                json={"model": model, "prompt": "", "stream": False, "keep_alive": 0},
            )
            self._check_status(response, model=model)
            payload = self._decode_object(response.text)
        except httpx.RequestError as exc:
            raise self._network_error(exc) from exc
        if "error" in payload:
            raise OllamaError(self._server_error(payload["error"], model))
        if payload.get("done") is not True:
            raise OllamaError(Text("Ollama returned an invalid 'done' marker."))

    def list_models(self) -> list[OllamaModel]:
        """Return the server's installed models from ``GET /api/tags``."""
        try:
            response = self._client.get("api/tags")
            self._check_status(response)
            payload = self._decode_object(response.text)
        except httpx.RequestError as exc:
            raise self._network_error(exc) from exc
        if "error" in payload:
            raise OllamaError(Text("Ollama: {detail}", detail=payload["error"]))
        models = payload.get("models")
        if not isinstance(models, list):
            raise OllamaError(Text("Ollama returned an invalid model list (expected 'models')."))
        result: list[OllamaModel] = []
        for item in models:
            if not isinstance(item, dict):
                raise OllamaError(Text("Ollama returned an invalid model entry."))
            name = item.get("name")
            size = item.get("size")
            if not isinstance(name, str) or not name.strip():
                raise OllamaError(Text("Ollama returned a model without a valid name."))
            if size is not None and (type(size) is not int or size < 0):
                raise OllamaError(Text("Ollama returned an invalid model size."))
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
            raise OllamaError(Text("Select an installed model before sending a message."))
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
                        raise OllamaError(Text("Ollama returned an invalid 'done' marker."))
                    message = chunk.get("message")
                    if message is not None:
                        if not isinstance(message, dict):
                            raise OllamaError(Text("Ollama returned an invalid chat message."))
                        # Thinking-capable models may send a reasoning-only
                        # message before their answer. Do not display reasoning
                        # as the assistant's answer or require answer text yet.
                        if "content" not in message and isinstance(message.get("thinking"), str):
                            content = ""
                        else:
                            content = message.get("content")
                        if not isinstance(content, str):
                            raise OllamaError(Text("Ollama returned an invalid chat message."))
                        if content:
                            yield content
                    elif not done:
                        raise OllamaError(Text("Ollama returned a chat chunk without a message."))
                    if done:
                        return
                if self._cancelled(cancel_event):
                    return
                raise OllamaError(
                    Text("Ollama disconnected before completing the reply. Try again.")
                )
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
            raise OllamaError(
                Text("Ollama returned malformed JSON. Check the server URL.")
            ) from exc
        if not isinstance(payload, dict):
            raise OllamaError(Text("Ollama returned an invalid response (expected a JSON object)."))
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
                Text(
                    "Model '{model}' is unavailable. Install it with 'ollama pull {model}', "
                    "then refresh the model list. {detail}",
                    model=model,
                    detail=detail,
                )
            )
        error = Text("Ollama HTTP {status}.", status=response.status_code)
        if detail:
            error = JoinedText((error, " " + detail), "")
        if response.status_code == 404:
            error = JoinedText(
                (error, Text(" Check the server URL; it must point to an Ollama server.")), ""
            )
        raise OllamaError(error)

    @staticmethod
    def _network_error(exc: httpx.RequestError) -> OllamaError:
        if isinstance(exc, httpx.TimeoutException):
            return OllamaError(
                Text(
                    "Ollama request timed out. The model may still be loading; "
                    "check Ollama and try again, or choose a smaller model."
                )
            )
        return OllamaError(
            Text("Cannot reach Ollama. Start it with 'ollama serve' and check the server URL.")
        )

    @staticmethod
    def _server_error(error: object, model: str) -> str:
        detail = error if isinstance(error, str) else Text("Unknown server error")
        message = Text("Ollama: {detail}", detail=detail)
        if "not found" in detail.lower():
            message = JoinedText(
                (
                    message,
                    Text(
                        " Install the model with 'ollama pull {model}' and refresh models.",
                        model=model,
                    ),
                ),
                "",
            )
        return message
