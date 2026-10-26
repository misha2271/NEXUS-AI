# NEXUS AI v1.0 — Game Guard foundation

This is the first **backend-only** v1.0 increment. It is not yet connected to
the Windows interface or background polling. It must not be advertised as an
automatic game optimizer in a released build.

- Match running processes by **explicitly configured executable filenames**.
- Handle missing or inaccessible process information without crashing.
- Detect transitions into and out of a gaming session, including several games.
- Recommend an Ollama unload only after opt-in and only for a model that NEXUS
  previously used. No process termination, power-plan changes, fan control,
  arbitrary model unloading or automatic model preload.
- Ollama is a shared service. Even a model previously used by NEXUS might be
  used by another app: an actual unload requires informed opt-in and must not
  be triggered while NEXUS has an active chat request.
- Game exit restores **availability of AI on demand**, not an automatic preload.

The Ollama REST API supports unloading with
`POST /api/generate` and `{"model": "...", "prompt": "", "keep_alive": 0}`.
Future UI integration must execute it off the UI thread, ask permission,
use timeouts and preserve Russian/English localization.
