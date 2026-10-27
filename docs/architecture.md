# NEXUS AI v1.0 architecture

v0.4 is based on the v0.3 commit in PR #2, `a9aee9b`. Existing settings and four
inference profiles retain their format and behavior. All v0.3 tests are retained.

| Component | Responsibility | Execution |
| --- | --- | --- |
| `telemetry.py` | CPU/RAM from psutil, optional NVIDIA NVML, named psutil temperature sensors | Serialized telemetry worker |
| `history.py` | Monotonic time-series, missing-reading gaps, 300-point / 600-second bound | UI thread, only on completed samples |
| `ui/dashboard.py` | Sidebar, scrollable module pages, responsive grids, Qt-painted charts | UI thread |
| `ui/window.py` | Route and chat state, settings, profile policy, job ownership and shutdown | UI thread |
| `workers.py` | Model discovery / streamed chat runnables, telemetry timer and resource cleanup | Dedicated pool / QThread |
| `ollama.py` | HTTP validation, NDJSON protocol, timeouts and response cleanup | Ollama worker, never on UI thread |
| `modules.py` | Explicit capabilities, validation status and future provider contracts | Registry data; future SDK probes must use workers |

## v1 service integration

`ui/v1.py` connects services to the existing eight routes; the v0.4 telemetry,
charts, profiles and instant RU/EN switching remain in place.

| Service | Worker boundary / persistence |
| --- | --- |
| Game Center | Serial pool for JSON, exact-name process scans and Ollama lifecycle calls. Game detection is opt-in; a separate effective mode preserves the persisted base mode. Confirmed process identity/liveness can establish known game exit despite unrelated protected processes. |
| Conversations | Serial task runner, short-lived SQLite transactions and optimistic revisions. Completed turns only, explicit resume/delete, plaintext local data. Writes drain during asynchronous close. |
| Storage / hardware | Fixed read-only PowerShell queries with timeout, no user command interpolation or elevation. Unsupported fields remain absent. |
| Gamepad | Fixed System32 XInput DLLs on Windows, four read-only slot snapshots, no device writes. |
| Updates | Worker HTTPS checks, pinned repository and redirect hosts, explicit download/major consent, byte-count and SHA256 verification; staging never executes or extracts a file. |
| Remote | Off by default; worker-owned HTTP/TLS server. Token, Host/Origin, replay and request bounds at ingress; allowlisted commands cross a main-thread queue. User-supplied TLS is mandatory on a LAN bind. |
| Voice | Provider protocols default deny audio; pure Russian/English allowlisted text intent parser. |

A successful chat grants ownership only to its requested model at the current
endpoint. Discovery does not grant ownership; changing endpoints forgets it.
Lifecycle operations serialize against NEXUS requests. An explicit next request
loads on demand and pauses auto-unload for the current game. Ollama residency is
shared: another client using that same model can still be affected by consented
unloading. NEXUS never kills Ollama, games or unrelated processes.

Every panel exposes nonblocking shutdown and a busy state. The main window waits
for these pools and the telemetry/chat workers through its existing shutdown timer;
service filesystem, process, socket and SQLite work stays off the UI thread.
Small preference writes retain the existing atomic SettingsStore path; no thread
join runs on the UI thread.
Native dialogs may wait for user input; they do not perform the worker operations.

## Sampling and rendering

The worker creates, samples and closes the collector on its own QThread. Its timer
uses profile-selected intervals (one to five seconds, with Smart pressure handling).
The initial CPU sample primes psutil. CPU and RAM failures do not hide surviving
sensors. Temperature labels preserve backend and sensor identity; they do not
rename ACPI or storage readings as CPU temperatures. Windows psutil does not supply
CPU temperature sensors, so they remain unavailable. GPU temperature comes only
from NVML when the device supports it.

Snapshots carry monotonic timestamps. History stores unavailable values as gaps,
including disconnected GPUs; it never carries old device values forward. Data is
not persisted, uploaded, or simulated. Charts share one history buffer and use
actual timestamps. Wide layouts show four cards / two chart columns; narrower
windows reflow existing widgets, preserve chat state, and scroll vertically.

## Cancellation and shutdown

Each HTTP job owns its client and closes it in the worker's context manager.
`cancel()` only sets a thread-safe event. Cancellation is cooperative between
received chunks; an outstanding synchronous read still has the v0.3 60-second
inactivity timeout (connect 5 seconds, write 15 seconds). This is not an immediate
socket abort or a total request deadline. A peer that keeps sending incomplete
lines may delay observing cancellation. No thread is forcibly terminated and no
HTTP client is synchronously closed on the UI thread.

Late cancelled discovery results and transport errors are discarded. Stopped or
failed partial chat replies never enter future request context. Text is appended
to the document in batches at most once per 30 ms, with an explicit final flush.
The window ignores its initial close while work is running, requests cancellation
and monitor stop, and uses a timer to check for completion. It never calls
`waitForDone()` on the UI thread. A global closing message explains delayed exit;
controls are disabled until every job and the monitor thread have exited.

## Hardware module extension contract

`ModuleSpec` describes navigation and the exact unsupported scope. Future
`IntegrationProvider` implementations must probe off the UI thread, own their SDK
resources, and publish `IntegrationStatus` including actual availability,
capabilities, validation status, and a reason. `IntegrationRegistry` defaults to
denial: availability alone cannot authorize a control. There are currently **no
registered hardware providers or command executors**. The UI's RGB, speaker RGB, fan, rumble, firmware and update installation
buttons remain disabled. Separate read-only diagnostics and consented update
downloads are connected through the v1 panels. Recording a status does not wire up or enable any device writes.

Before exposing RGB or fan writes, a future implementation needs a supported SDK,
physical-device testing, supported-model discovery, cancellation/cleanup tests,
capability checks at the command boundary, safe ranges, and visible error reporting.
No guessed HID commands, OS tuning, firmware installation or simulated health
percentages are part of this version. Update Center can check and verify a
consented download; it never installs updates.

## Validation boundaries

Automated tests cover service/NDJSON behavior, settings, four profiles, telemetry
failures, Qt worker ownership, responsive navigation, history gaps, capability
denial and cancellation. Native Windows Actions builds onefile and onedir EXEs,
then launches each twice with a Python-free PATH and isolated APPDATA. Reports and
screenshots exercise actual frozen Qt, host CPU/RAM and settings persistence.

These checks do not validate real Ollama inference, an installed NVIDIA driver,
physical GPU temperature accuracy, RGB devices, Windows 11 desktop interactions,
the winget bootstrap, code signing, or installation on a clean user's PC. Those
remain manual acceptance requirements. Actions uploads tested build artifacts;
it also validates a per-user Inno Setup installer, but creates no releases, tags
or automatic merges.

## Localization

`i18n.py` holds pure, locale-independent structured messages (`Text`, `JoinedText`)
and rendering. English source templates are the catalog keys; `translations.py`
contains their Russian equivalents. Placeholder parity and catalog coverage are
checked automatically. No translation service or global process locale is used.

Each window owns a `Translator` in `ui/localization.py`. It retains canonical
captions and QObject-lifetime-managed bindings, updates existing widgets and open
menus in place, and does not recreate workers, history buffers, or chat state.
Qt-created action wrappers stay alive until their QObject is destroyed. Transcripts
separate application notices from raw user/model text so language changes cannot
alter conversation contents. The retained presentation source is bounded.

Settings stores `language` as `ru` or `en`, defaulting to `ru`. Profile display names
are localized while combo item data, persisted IDs and inference options remain
canonical. The language picker saves immediately; cancelling the dialog does not
undo that explicit choice. Changing only language never clears a chat or restarts
model discovery. During a request, Settings permits language selection but locks
and validates endpoint changes. Failed persistence leaves the previous locale in
use and shows a translated error.

Worker error signals carry structured objects rather than prematurely formatting
strings. Delayed results, existing notifications, chart values and errors therefore
follow the current language. Unknown third-party diagnostics remain original data
inside translated application messages. Standard editing and scrollbar menus have
localized labels while retaining shortcuts and Qt scrolling actions.

Frozen Windows self-tests additionally verify Russian startup, switch to English,
check the saved preference, and restore Russian. Both language screenshots are
uploaded with each executable's smoke reports. They do not require external `.qm`
resources or Qt Linguist tools.
