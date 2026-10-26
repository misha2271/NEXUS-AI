# Actual v0.4 screenshots

These PNGs were captured from the running PySide6 application on the Linux cloud
host using the offscreen Qt platform. CPU/RAM and chart samples came from the real
collector over twelve seconds. No sample data, GPU values, models, or assistant
answers were injected. This host has no working NVML driver, readable temperature
sensors or Ollama server, and the UI shows those limitations explicitly.

- [Russian overview, 1440 × 1150](overview.png): live CPU/RAM, history and unavailable sensors.
- [Russian assistant, 1280 × 860](assistant.png): actual offline endpoint, disabled send.
- [RGB Studio, 1280 × 860](rgb-unavailable.png): no provider and disabled controls.
- [Compact dashboard, 780 × 900](compact.png): reflowed cards and single-column charts.

Russian is the default language in these captures. The English comparison uses
its own temporary preferences and real host samples, not edited image text.

- [Russian Settings / language selector](settings.png).
- [English overview](en/overview.png).
- [English Settings](en/settings.png).

Reproduce from the repository root with development dependencies installed:

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/capture_screenshots.py
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/capture_screenshots.py --language en --output /tmp/nexus-en-captures
```

The script uses temporary settings, starts real workers, captures the widgets,
and drains workers through the normal asynchronous close path. Measurements will
vary by host. These are Linux captures, not evidence of a physical Windows 11
session. Native Windows executable self-tests additionally capture PNGs in
`dist/smoke/`, uploaded with each build's smoke-report artifact.

Native frozen probes capture both Russian and English, and confirm saved language
preferences before restoring Russian for the next launch.
