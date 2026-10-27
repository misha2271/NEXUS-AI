"""Opt-in, authenticated, bounded LAN remote control with a Qt-safe queue bridge.

This is not an Internet-facing service. HTTP is accepted only on loopback for
local development; an actual iPhone/LAN connection requires a supplied trusted
TLS certificate. Device control, arbitrary prompts, files and shell commands are
not exposed. Tokens are generated in memory and never persisted or logged here.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import socket
import ssl
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from queue import Empty, Full, Queue
from socketserver import ThreadingMixIn
from typing import Callable
from urllib.parse import urlsplit

from nexus_ai.i18n import Text, render
from nexus_ai.profiles import PROFILE_NAMES

MAX_BODY = 4096
MAX_RESPONSE = 32768
COMMANDS = frozenset({"status", "stop_generation", "set_profile"})


class RemoteError(RuntimeError):
    """A safe, user-facing remote-control configuration or dispatch failure."""


@dataclass(frozen=True)
class RemoteConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 0
    certfile: str | None = None
    keyfile: str | None = None
    allowed_hosts: tuple[str, ...] = ()
    max_connections: int = 8
    requests_per_minute: int = 60
    request_timeout: float = 8.0


def generate_token() -> str:
    """Return 256 bits of cryptographic randomness; caller must not log it."""
    return secrets.token_urlsafe(32)


def validate_token(token: str) -> None:
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", token):
        raise RemoteError(
            Text("Remote control requires a token containing at least 32 random bytes.")
        )
    try:
        decoded = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except ValueError as exc:
        raise RemoteError(Text("The remote token is invalid.")) from exc
    if len(decoded) < 32:
        raise RemoteError(Text("The remote token is invalid."))


def validate_config(config: RemoteConfig) -> str:
    """Validate without binding; return the normalized literal bind address."""
    host = "127.0.0.1" if config.host == "localhost" else config.host
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise RemoteError(Text("Bind remote control to a specific local IP address.")) from exc
    if address.is_unspecified or address.is_multicast:
        raise RemoteError(Text("Wildcard and multicast remote-control bindings are not allowed."))
    if type(config.port) is not int or not 0 <= config.port <= 65535:
        raise RemoteError(Text("The remote-control port must be between 0 and 65535."))
    if type(config.enabled) is not bool:
        raise RemoteError(Text("Remote control must be explicitly enabled."))
    if (
        type(config.max_connections) is not int
        or type(config.requests_per_minute) is not int
        or not 1 <= config.max_connections <= 32
        or not 1 <= config.requests_per_minute <= 600
    ):
        raise RemoteError(Text("The remote connection or rate limit is invalid."))
    if type(config.request_timeout) not in (int, float) or not 1 <= config.request_timeout <= 30:
        raise RemoteError(Text("The remote request timeout must be between 1 and 30 seconds."))
    if bool(config.certfile) != bool(config.keyfile):
        raise RemoteError(Text("Supply both the TLS certificate and its private key."))
    if not address.is_loopback and not config.certfile:
        raise RemoteError(
            Text("LAN remote control requires a trusted TLS certificate and private key.")
        )
    for path in (config.certfile, config.keyfile):
        if path and not Path(path).is_file():
            raise RemoteError(Text("A configured TLS certificate or key file is missing."))
    if not isinstance(config.allowed_hosts, (tuple, list)) or len(config.allowed_hosts) > 16:
        raise RemoteError(Text("A remote-control allowed hostname is invalid."))
    for allowed in config.allowed_hosts:
        if not isinstance(allowed, str) or not _valid_host(allowed):
            raise RemoteError(Text("A remote-control allowed hostname is invalid."))
    return str(address)


def _valid_host(host: str) -> bool:
    if not host or len(host) > 253 or any(c in host for c in "/\\@?#\r\n"):
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part)
            for part in host.split(".")
        )


def validate_command(command: object, params: object) -> tuple[str, dict]:
    if not isinstance(command, str) or command not in COMMANDS or not isinstance(params, dict):
        raise RemoteError(Text("This remote command is not approved."))
    if command == "set_profile":
        if set(params) != {"profile"} or params["profile"] not in PROFILE_NAMES:
            raise RemoteError(Text("Choose a supported performance profile."))
    elif params:
        raise RemoteError(Text("This remote command does not accept parameters."))
    return command, dict(params)


@dataclass
class _Pending:
    command: str
    params: dict
    ready: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    state: str = "pending"
    result: dict | None = None
    error: bool = False


class RemoteCommandQueue:
    """HTTP threads submit; a QTimer drains on the UI thread. No Qt imports here.

    A pending request that times out is cancelled and cannot execute later. An
    already-running handler cannot be rolled back; approved writes are idempotent.
    """

    def __init__(self, max_pending: int = 32):
        self._queue: Queue[_Pending] = Queue(maxsize=max_pending)
        self._closed = False
        self._lock = threading.Lock()

    def submit(self, command: str, params: dict, timeout: float = 2.0) -> dict:
        command, params = validate_command(command, params)
        pending = _Pending(command, params)
        with self._lock:
            if self._closed:
                raise RemoteError(Text("Remote command processing is stopped."))
            try:
                self._queue.put_nowait(pending)
            except Full as exc:
                raise RemoteError(Text("The remote command queue is full.")) from exc
        if not pending.ready.wait(timeout):
            with pending.lock:
                if pending.state == "pending":
                    pending.state = "cancelled"
            raise RemoteError(Text("The remote command timed out. Check status before retrying."))
        if pending.error or pending.result is None:
            raise RemoteError(Text("The remote command could not be completed."))
        return pending.result

    def drain(self, handler: Callable[[str, dict], dict], limit: int = 8) -> int:
        """Call only on the main thread; handler must be fast and nonblocking."""
        processed = 0
        for _ in range(max(0, limit)):
            try:
                pending = self._queue.get_nowait()
            except Empty:
                break
            with pending.lock:
                if pending.state == "cancelled":
                    continue
                pending.state = "running"
            try:
                result = handler(pending.command, pending.params)
                if not isinstance(result, dict):
                    raise TypeError("Remote handlers must return objects")
                pending.result = result
            except Exception:
                pending.error = True
            finally:
                with pending.lock:
                    pending.state = "done"
                pending.ready.set()
            processed += 1
        return processed

    def close(self) -> None:
        with self._lock:
            self._closed = True
            while True:
                try:
                    pending = self._queue.get_nowait()
                except Empty:
                    break
                with pending.lock:
                    pending.state = "cancelled"
                    pending.error = True
                pending.ready.set()


def _reject_constant(_):
    raise ValueError("Non-finite JSON numbers are not accepted")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON fields are not accepted")
        result[key] = value
    return result


class _Limits:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._requests: dict[str, deque] = {}
        self._nonces: dict[str, float] = {}
        self._lock = threading.Lock()

    def request(self, address: str) -> bool:
        now = time.monotonic()
        with self._lock:
            self._requests = {
                ip: times for ip, times in self._requests.items() if times and now - times[-1] < 60
            }
            if address not in self._requests and len(self._requests) >= 256:
                return False
            times = self._requests.setdefault(address, deque())
            while times and now - times[0] >= 60:
                times.popleft()
            if len(times) >= self.per_minute:
                return False
            times.append(now)
            return True

    def nonce(self, nonce: object) -> bool:
        if not isinstance(nonce, str) or not re.fullmatch(r"[a-f0-9]{32,64}", nonce):
            return False
        now = time.monotonic()
        with self._lock:
            self._nonces = {
                value: stamp for value, stamp in self._nonces.items() if now - stamp < 300
            }
            if nonce in self._nonces or len(self._nonces) >= 4096:
                return False
            self._nonces[nonce] = now
            return True


class _BoundedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = False

    def server_bind(self):
        # HTTPServer's default calls getfqdn; binding must not require DNS.
        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()
        self.server_name, self.server_port = self.server_address[:2]

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        with self.clients_lock:
            self.clients.add(request)
        try:
            super().process_request(request, client_address)
        except Exception:
            with self.clients_lock:
                self.clients.discard(request)
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        original = request
        try:
            request.settimeout(3)
            if self.tls_context is not None:
                request = self.tls_context.wrap_socket(request, server_side=True)
                with self.clients_lock:
                    self.clients.discard(original)
                    self.clients.add(request)
            super().process_request_thread(request, client_address)
        except (OSError, ssl.SSLError):
            self.shutdown_request(request)
        finally:
            with self.clients_lock:
                self.clients.discard(original)
                self.clients.discard(request)
            self.slots.release()

    def handle_error(self, request, client_address):
        # HTTP errors must not dump authentication headers or command bodies.
        pass

    def close_clients(self):
        with self.clients_lock:
            clients = tuple(self.clients)
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class RemoteServer:
    def __init__(self, config: RemoteConfig, token: str, dispatcher: Callable[[str, dict], dict]):
        self.config = config
        self.host = validate_config(config)
        validate_token(token)
        self._token = token
        self._dispatcher = dispatcher
        self._limits = _Limits(config.requests_per_minute)
        self._server = None
        self._thread = None

    @property
    def address(self) -> tuple[str, int] | None:
        return (self.host, self._server.server_port) if self._server else None

    @property
    def origin(self) -> str | None:
        if not self.address:
            return None
        host, port = self.address
        host = f"[{host}]" if ":" in host else host
        return f"{'https' if self.config.certfile else 'http'}://{host}:{port}"

    def start(self) -> str:
        if not self.config.enabled:
            raise RemoteError(Text("Remote control is disabled. Enable it explicitly to start."))
        if self._server is not None:
            raise RemoteError(Text("Remote control is already running."))
        context = None
        if self.config.certfile:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            try:
                context.load_cert_chain(self.config.certfile, self.config.keyfile)
            except (OSError, ssl.SSLError) as exc:
                raise RemoteError(Text("The TLS certificate and key could not be loaded.")) from exc
        server_type = (
            type("_IPv6Server", (_BoundedServer,), {"address_family": socket.AF_INET6})
            if ":" in self.host
            else _BoundedServer
        )
        server = server_type((self.host, self.config.port), self._handler())
        server.slots = threading.BoundedSemaphore(self.config.max_connections)
        server.clients_lock = threading.Lock()
        server.clients = set()
        server.tls_context = context
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.1},
            name="nexus-remote-listener",
            daemon=True,
        )
        try:
            self._thread.start()
        except Exception:
            server.close_clients()
            server.server_close()
            self._server = self._thread = None
            raise
        return self.origin

    def stop(self) -> None:
        server, thread = self._server, self._thread
        if server is None:
            return
        server.shutdown()
        server.close_clients()
        server.server_close()
        if thread is not None:
            thread.join(timeout=2)
        self._server = self._thread = None

    def _handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"
            server_version = "NEXUS"
            sys_version = ""
            rbufsize = 8192

            def log_message(self, *_):
                pass

            def handle(self):
                def expire():
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

                deadline = threading.Timer(owner.config.request_timeout, expire)
                deadline.daemon = True
                deadline.start()
                try:
                    super().handle()
                finally:
                    deadline.cancel()

            def _respond(self, status, payload, content_type="application/json; charset=utf-8"):
                try:
                    data = (
                        payload
                        if isinstance(payload, bytes)
                        else json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(
                            "utf-8"
                        )
                    )
                except (TypeError, ValueError):
                    status, data = 503, b'{"error":"invalid_response"}'
                if len(data) > MAX_RESPONSE:
                    status, data = 503, b'{"error":"response_too_large"}'
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Permissions-Policy", "microphone=(), camera=(), geolocation=()")
                self.send_header("Content-Security-Policy", _csp())
                self.end_headers()
                if self.command != "HEAD":
                    try:
                        self.wfile.write(data)
                    except OSError:
                        pass
                self.close_connection = True

            def _error(self, status, code, message):
                language = (
                    "en" if getattr(self, "headers", {}).get("X-Nexus-Language") == "en" else "ru"
                )
                self._respond(status, {"error": code, "message": render(message, language)})

            def send_error(self, code, message=None, explain=None):
                self._error(code, "invalid_request", Text("The remote request was rejected."))

            def _common(self):
                if not owner._limits.request(self.client_address[0]):
                    self._error(
                        429, "rate_limited", Text("Too many remote requests. Try again later.")
                    )
                    return False
                if self.path not in ("/", "/api/status", "/api/command"):
                    self._error(404, "not_found", Text("The remote endpoint was not found."))
                    return False
                hosts = self.headers.get_all("Host", [])
                if len(hosts) != 1 or len(hosts[0]) > 300:
                    self._error(403, "host_denied", Text("This remote hostname is not approved."))
                    return False
                try:
                    parsed = urlsplit("//" + hosts[0])
                    hostname = parsed.hostname
                    port = parsed.port or (443 if owner.config.certfile else 80)
                except ValueError:
                    hostname = port = None
                    parsed = None
                approved = {
                    owner.host.casefold(),
                    *(h.casefold() for h in owner.config.allowed_hosts),
                }
                if ipaddress.ip_address(owner.host).is_loopback:
                    approved.add("localhost")
                if (
                    parsed is None
                    or not hostname
                    or hostname.casefold() not in approved
                    or port != self.server.server_port
                    or parsed.username
                    or parsed.password
                    or parsed.path
                    or parsed.query
                    or parsed.fragment
                ):
                    self._error(403, "host_denied", Text("This remote hostname is not approved."))
                    return False
                scheme = "https" if owner.config.certfile else "http"
                origins = self.headers.get_all("Origin", [])
                expected = f"{scheme}://{hosts[0]}"
                if len(origins) > 1 or (origins and origins[0] != expected):
                    self._error(
                        403, "origin_denied", Text("Cross-origin remote requests are not allowed.")
                    )
                    return False
                if self.headers.get("Sec-Fetch-Site") == "cross-site":
                    self._error(
                        403, "origin_denied", Text("Cross-origin remote requests are not allowed.")
                    )
                    return False
                if self.headers.get_all("Transfer-Encoding"):
                    self._error(400, "invalid_request", Text("The remote request was rejected."))
                    return False
                return True

            def _authenticated(self):
                values = self.headers.get_all("Authorization", [])
                if len(values) != 1 or len(values[0]) > 256 or not values[0].startswith("Bearer "):
                    self._error(401, "unauthorized", Text("Remote authentication failed."))
                    return False
                supplied = values[0][7:]
                if not supplied.isascii() or not hmac.compare_digest(supplied, owner._token):
                    self._error(401, "unauthorized", Text("Remote authentication failed."))
                    return False
                return True

            def _dispatch(self, command, params):
                try:
                    result = owner._dispatcher(command, params)
                    if not isinstance(result, dict):
                        raise TypeError("Invalid dispatcher result")
                except Exception:
                    self._error(
                        503,
                        "command_unavailable",
                        Text("The remote command could not be completed."),
                    )
                    return
                self._respond(200, result)

            def do_GET(self):
                if not self._common():
                    return
                if self.path == "/":
                    self._respond(200, _page(), "text/html; charset=utf-8")
                elif self.path == "/api/status" and self._authenticated():
                    self._dispatch("status", {})
                elif self.path == "/api/command":
                    self._error(405, "method_not_allowed", Text("Use POST for remote commands."))

            def do_POST(self):
                if not self._common() or not self._authenticated():
                    return
                if self.path != "/api/command":
                    self._error(405, "method_not_allowed", Text("Use GET for remote status."))
                    return
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,6}", lengths[0]):
                    self._error(
                        411, "length_required", Text("A bounded request length is required.")
                    )
                    return
                length = int(lengths[0])
                if not 0 < length <= MAX_BODY:
                    self._error(
                        413, "body_too_large", Text("The remote request body is too large.")
                    )
                    return
                if (
                    len(self.headers.get_all("Content-Type", [])) != 1
                    or self.headers.get_content_type() != "application/json"
                ):
                    self._error(415, "content_type", Text("Remote commands require JSON."))
                    return
                try:
                    payload = json.loads(
                        self.rfile.read(length).decode("utf-8"),
                        parse_constant=_reject_constant,
                        object_pairs_hook=_unique_object,
                    )
                    if not isinstance(payload, dict) or set(payload) != {
                        "command",
                        "params",
                        "nonce",
                    }:
                        raise ValueError("Invalid schema")
                    command, params = validate_command(payload["command"], payload["params"])
                except (ValueError, UnicodeError, RemoteError, RecursionError):
                    self._error(
                        400, "invalid_command", Text("This remote command is not approved.")
                    )
                    return
                if not owner._limits.nonce(payload["nonce"]):
                    self._error(
                        409,
                        "nonce_rejected",
                        Text("The remote request nonce is invalid or was already used."),
                    )
                    return
                self._dispatch(command, params)

            def do_OPTIONS(self):
                if self._common():
                    self._error(
                        405, "method_not_allowed", Text("This remote method is not allowed.")
                    )

            do_HEAD = do_OPTIONS
            do_PUT = do_OPTIONS
            do_PATCH = do_OPTIONS
            do_DELETE = do_OPTIONS

        return Handler


WEB_MESSAGES = (
    "Remote control",
    "Russian",
    "English",
    "Pairing token",
    "Connect",
    "Status",
    "Stop generation",
    "Performance profile",
    "Apply profile",
    "Keep this page on a trusted local network. No hardware writes are available.",
    "Enter the token shown in NEXUS AI. It is kept only in this page memory.",
    "Connection failed. Verify the certificate, address and token.",
    "Connected",
    "Smart",
    "Gaming",
    "Maximum AI",
    "Eco",
)
_STYLE = (
    "body{font:16px system-ui;background:#0c1017;color:#e6eaf2;max-width:"
    "600px;margin:2rem auto;padding:1rem}input,select,button{font:inherit"
    ";padding:.8rem;margin:.3rem 0;border-radius:8px;max-width:100%;box-s"
    "izing:border-box}input{width:100%}button{background:#8ce0c4;color:#1"
    "0251d;border:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;backg"
    "round:#16202d;padding:1rem}label{display:block;margin-top:1rem}small"
    "{color:#b5c1d0}"
)
_SCRIPT = (
    "const $=id=>document.getElementById(id);let token='';let "
    "lang='ru';const t=s=>catalog[lang][s]||s;function translate(){docume"
    "nt.documentElement.lang=lang;document.querySelectorAll('[data-t]').f"
    "orEach(e=>e.textContent=t(e.dataset.t));}async function "
    "call(command,params={}){try{const headers={'Authorization':'Bearer "
    "'+token,'X-Nexus-Language':lang};let "
    "response;if(command==='status'){response=await fetch('/api/status',{"
    "headers,cache:'no-store'});}else{headers['Content-Type']='applicatio"
    "n/json';const bytes=crypto.getRandomValues(new Uint8Array(16));const"
    " nonce=Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');"
    "response=await fetch('/api/command',{method:'POST',headers,body:JSON"
    ".stringify({command,params,nonce}),cache:'no-store'});}const "
    "result=await response.json();$('result').textContent=JSON.stringify("
    "result,null,2);if(!response.ok)throw new Error('rejected');$('connec"
    "tion').textContent=t('Connected');}catch(_){$('connection').textCont"
    "ent=t('Connection failed. Verify the certificate, address and token."
    "');}}$('language').onchange=()=>{lang=$('language').value;translate("
    ");};$('connect').onclick=()=>{token=$('token').value;$('token').valu"
    "e='';call('status');};$('status').onclick=()=>call('status');$('stop"
    "').onclick=()=>call('stop_generation');$('apply').onclick=()=>call('"
    "set_profile',{profile:$('profile').value});translate();"
)


def _page() -> bytes:
    catalog = {
        language: {text: render(Text(text), language) for text in WEB_MESSAGES}
        for language in ("ru", "en")
    }
    encoded = json.dumps(catalog, ensure_ascii=False).replace("<", "\\u003c")
    html = (
        '<!doctype html><html lang="ru"><meta charset="utf-8"><meta '
        'name="viewport" '
        'content="width=device-width,initial-scale=1"><title>NEXUS '
        "AI</title><style>STYLE</style><main><h1>NEXUS AI · <span "
        'data-t="Remote control"></span></h1><select id="language" '
        'aria-label="Language"><option value="ru">Русский</option><option '
        'value="en">English</option></select><p data-t="Keep this page on a '
        'trusted local network. No hardware writes are available."></p><label'
        ' for="token" data-t="Pairing token"></label><input id="token" '
        'type="password" autocomplete="off" autocapitalize="off" '
        'spellcheck="false"><small data-t="Enter the token shown in NEXUS AI.'
        ' It is kept only in this page memory."></small><p><button '
        'id="connect" data-t="Connect"></button> <button id="status" '
        'data-t="Status"></button> <button id="stop" data-t="Stop '
        'generation"></button></p><label for="profile" data-t="Performance '
        'profile"></label><select id="profile"><option value="Smart" '
        'data-t="Smart"></option><option value="Gaming" '
        'data-t="Gaming"></option><option value="Maximum AI" data-t="Maximum '
        'AI"></option><option value="Eco" '
        'data-t="Eco"></option></select><button id="apply" data-t="Apply '
        'profile"></button><p id="connection" role="status"></p><pre id="resu'
        'lt"></pre></main><script>CATALOG</script><script>SCRIPT</script></ht'
        "ml>"
    )
    return (
        html.replace("STYLE", _STYLE)
        .replace("CATALOG", "const catalog=" + encoded + ";")
        .replace("SCRIPT", _SCRIPT)
        .encode("utf-8")
    )


def _csp() -> str:
    catalog = {
        language: {text: render(Text(text), language) for text in WEB_MESSAGES}
        for language in ("ru", "en")
    }
    encoded = json.dumps(catalog, ensure_ascii=False).replace("<", "\\u003c")
    scripts = ("const catalog=" + encoded + ";", _SCRIPT)
    hashes = [
        "'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'"
        for s in scripts
    ]
    style = base64.b64encode(hashlib.sha256(_STYLE.encode()).digest()).decode()
    return (
        "default-src 'none'; connect-src 'self'; script-src "
        + " ".join(hashes)
        + f"; style-src 'sha256-{style}'; "
        + "frame-ancestors 'none'; form-action 'none'; base-uri 'none'"
    )
