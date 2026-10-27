# v1.0 release checklist / Подготовка релиза

This checklist authorizes no merge, tag, release, installer or hardware writes.
Этот список не разрешает слияние, создание тега или публикацию релиза.

## Dependency and merge order / Зависимости и порядок слияния

1. Review and approve PR #2 (`feature/nexus-ai-v0.3` → `main`).
2. Review PR #3 (`feature/nexus-ai-v0.4-dashboard` → `main`) after #2. Resolve
   overlaps and rerun checks; it preserves the v0.3 source and adds localized UI.
3. Keep draft PR #4 (`feature/nexus-ai-v1.0` → v0.4 branch) while #3 is unmerged.
   After #3 merges, explicitly retarget #4 to main, inspect the resulting diff,
   synchronize without discarding commits and rerun all six CI configurations.
4. Merge only after explicit owner approval. Publish a version only after another
   explicit release approval and the acceptance checks below.

## Automated acceptance / Автоматические проверки

- [ ] Six CI jobs: Linux and Windows × Python 3.11, 3.12, 3.13, exact final SHA.
- [ ] Ruff, formatting, compileall, Bandit and dependency audit; no ignored CVEs.
- [ ] Native Windows onefile EXE and complete Portable ZIP built at final SHA.
- [ ] Both EXEs launch twice without Python on PATH; RU/EN, persistent settings,
      CPU/RAM and clean shutdown smoke probes pass.
- [ ] Per-user `NEXUS-AI-Setup-1.0.0.exe`: silent install, installed EXE RU/EN smoke
      without Python, silent uninstall, preserved user preferences/conversations.
- [ ] SHA256SUMS matches all three downloads; source and smoke reports downloadable.
- [ ] PR validation report records exact counts, SHA, run and artifact URLs.

## Manual Windows 11 acceptance / Проверка на Windows 11

- [ ] Clean x64 computer: launch both builds with no Python installation; compact
      Russian/English navigation, settings migration, restart and normal exit.
- [ ] Real Ollama: discovery, streamed reply, stop during stalled network, concurrent
      refresh attempts, missing model/error handling, completed conversation restart.
- [ ] Configured real game: Gaming activation, exact EXE matching, concurrent games,
      protected process handling, previous profile restoration and no process kills.
- [ ] Confirm default-off unloading; explicitly opt in, verify API ACK and actual
      VRAM change. Never unload an unowned model or overlap a NEXUS request.
      Check shared-model effects with another Ollama client before accepting.
- [ ] SSD: compare available Windows counters to OS output. Missing temperatures
      remain unavailable; consumed wear is never shown as remaining health.
- [ ] Real Xbox controller: XInput button/stick snapshots, disconnect/reconnect;
      no Elite identity/paddle/rumble claim.
- [ ] iPhone: trusted LAN TLS, pairing/token lifecycle, unauthorized/Host/Origin/replay
      rejection, approved status/stop/profile only, clean listener shutdown.
- [ ] Update checker with an approved future stable release: hash/size mismatch,
      cancellation, redirect rejection and separate major-version approval.
      Staging must never execute or install an update.

## Unsupported / Не поддерживается

MSI Mystic Light writes, G560 RGB/audio, fan/cooling writes, Elite paddles/remapping,
firmware updates, microphone/STT/TTS, update installation and code signing remain
unsupported. Device names from inventory are not proof of SDK compatibility.
Physical hardware validation is outstanding; CI tests cannot replace it.
