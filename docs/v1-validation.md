# v1.0 validation / Проверка v1.0

Validated in the existing Linux cloud workspace on 2026-10-27, preserving the
v0.4 branch and PR #4 history. No branch merge, tag or release was created.

- Python 3.12: **565 pytest tests passed** in 8.81 s, including preserved v0.4
  tests, Game Guard state/HTTP tests, GUI integration, persistent conversation
  relaunch, cancellation, asynchronous close, Russian/English and remote security.
- `ruff check .`, `ruff format --check .`, `compileall` and `git diff --check`: pass.
- Wheel and source distribution: built successfully at version 1.0.0.
- Source application `--self-test`: passed with actual CPU/RAM and isolated settings.
- Bandit: zero medium/high severity findings at medium+ confidence.
- pip-audit: 54 installed distributions, zero known dependency vulnerabilities;
  unpublished local source is scanned separately by Bandit.
- Live official GitHub Releases request: no visible published release or access
  denied (HTTP 404). Download integrity, redirects, cancellation and major-version
  approval were tested with HTTP fixtures, without publishing a release.
- Real Linux offscreen RU/EN screenshots: [gallery](screenshots/README.md).

## Windows artifacts / Артефакты Windows

Native x64 Windows EXE and Portable ZIP builds run on GitHub Actions for this
feature branch. Both executable layouts must launch successfully twice with
isolated APPDATA and no Python on PATH; probes check real CPU/RAM, saved settings,
Russian startup and switching to English. Checksums and smoke reports accompany
successful artifacts. See the latest run for this exact commit in
[Windows executable builds](https://github.com/misha2271/NEXUS-AI/actions/workflows/windows-build.yml).
Final run/artifact URLs are recorded in PR #4 after the native run completes.

Windows build results are separate from physical acceptance. This workspace has
no Windows games, Ollama GPU server, SSD SMART device, Xbox, MSI, G560 or iPhone.
Real device behavior, game timing, VRAM release and trusted iPhone LAN TLS still
require tests on the user's equipment. No audio backend, Elite-specific feature,
RGB/fan write, update installer or code signing is claimed.

Все 565 локальных теста прошли; проверки оборудования физически не проводились.
Успешная сборка EXE подтверждает упаковку и запуск интерфейса, но не наличие
подключённого оборудования. Для живой проверки нужны компьютер Windows и
реальные устройства. Публикация релиза и слияние веток не выполняются.
