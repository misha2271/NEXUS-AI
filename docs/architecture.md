# NEXUS AI v0.4 architecture

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
registered hardware providers or command executors**. The UI's RGB, speaker RGB,
fan, rumble, SMART and update buttons remain disabled regardless of placeholder
navigation. Recording a status does not wire up or enable any device writes.

Before exposing RGB or fan writes, a future implementation needs a supported SDK,
physical-device testing, supported-model discovery, cancellation/cleanup tests,
capability checks at the command boundary, safe ranges, and visible error reporting.
No guessed HID commands, OS tuning, firmware installation, downloads, or simulated
health percentages are part of this version. Update Center displays the installed
version only; it does not check for or install updates.

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
it does not create releases, tags, installers or automatic merges.
