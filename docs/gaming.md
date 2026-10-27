# Game detection and Ollama lifecycle / Игровые профили и управление Ollama

## English

### Working interfaces

`gaming.py` saves explicitly configured profiles in `games.json` beside normal
settings. Detection and model unloading are **disabled by default**. The Game Center
in the existing Gaming page can add, select, edit and remove games, including
semicolon-separated executable names and an explicit per-game unload checkbox.
New profiles use Gaming mode; all four existing modes remain supported by the
persistent configuration and base-mode selector. Each profile supplies an exact
executable basename (or several), one of the existing canonical mode IDs `Smart`,
`Gaming`, `Maximum AI`, `Eco`, an unload preference and a priority from -100 to 100.
No wildcard matching, executable paths, launcher heuristics or invented game list
is used. Matching is case-insensitive, and equal priorities use configured order.
Changing these profiles never kills or starts a process or changes Windows tuning.

`ProcessDetector.scan()` reads actual names through `psutil.process_iter(attrs=["name"])`.
Enumeration happens in a background job. Removed processes are ignored. Protected
or unnamed processes make the scan incomplete; if no new game is confirmed,
`LifecycleController` retains the previously confirmed game rather than falsely
reporting that it ended. The detector also retains positively identified psutil
Process objects: their identity-aware `is_running()` checks can establish that the
known game session ended even when unrelated protected Windows process names
remain unreadable. Failed liveness checks never prove exit. Disabling detection,
a complete no-match scan, or confirmed known-session exit restores the user's
selected base mode. This is intentionally conservative when process access is
restricted. It does not perform FPS capture or classify unknown games.

The Ollama client implements the documented APIs:

| Operation | API and request | Required acknowledgement |
| --- | --- | --- |
| Running models | `GET /api/ps` | A validated `models` array from the actual server |
| Unload selected model | `POST /api/generate` with named model, empty prompt, `stream:false`, `keep_alive:0` | `done:true`, `done_reason:"unload"`; response/model fields validated when present |
| Explicit warm load | Same generate endpoint with empty prompt and positive finite retention | Completed empty response for the matching model |

No `/api/delete`, `ollama stop` shell invocation, process termination or model-file
removal is used. Warm load never pulls/downloads a model. Missing models or failed
acknowledgements are reported as errors; a successful HTTP status alone is not
reported as a completed unload. Older servers without the documented unload
acknowledgement are rejected rather than guessed to support it.

### Ownership and demand

Automatic unloading is limited to a model successfully used by NEXUS and requires
a confirmed opted-in game profile. An active NEXUS request defers unloading until
it finishes. Failed unloads are not retried every polling tick; retry becomes
possible after another successful NEXUS request or a game transition.

Ollama residency is **server-wide per model, not isolated per client**. A different
application using that same model can still be affected. Opt-in consent must make
this explicit. NEXUS does not adopt every model returned by `/api/ps` as its own.

Game exit restores the selected mode but **does not eagerly load a model**. A new
explicit chat naturally loads its selected model through `/api/chat`. The explicit
restore action can request a warm load through the supported generate API.
`request_restore()` suspends automatic re-unloading for the current game, so a
manual restore is not immediately undone; a later game transition or manual
unload resets that override. It does not run network I/O itself.

### Integration contract

- `GameProfileStore.load()` returns disabled defaults on missing/corrupt/oversized
  data; corrupt originals are preserved. Writes validate first and replace atomically.
- `ProcessDetector.scan(config)` returns `GameDetection(active, matched_processes,
  complete, status, confirmed_exit=False)` and must run off the UI thread.
- `LifecycleController(base_mode)` records the user's base mode. `observe`,
  `set_busy` and `set_base_mode` return `LifecycleDecision` values. Each returned
  decision can reserve an unload operation; callers must execute that action in
  a worker and then call `unloaded(model)` or `unload_failed(model)`.
- `note_model_used(model)` is called only after a successful explicit NEXUS request.
  Do not infer ownership from the selected combo item or the server's loaded list.
- `pending_operation` must gate conflicting manual load/chat operations. Never
  close an HTTP transport or wait for a worker synchronously on the Qt UI thread.

HTTP reads retain the client's existing timeouts. This implementation neither
starts an Ollama daemon nor configures its operating-system service.

### Sources and validation limits

Official Ollama API documentation was retrieved from the upstream repository:

- [Generate load/unload examples](https://github.com/ollama/ollama/blob/main/docs/api.md#generate-a-completion)
- [List running models](https://github.com/ollama/ollama/blob/main/docs/api.md#list-running-models)
- [psutil process iteration](https://psutil.readthedocs.io/en/latest/#psutil.process_iter)

Protocol tests exercise HTTP payloads, strict acknowledgements and failures against
an in-memory HTTP transport. Process tests inject enumerator fixtures; persistence
and lifecycle transitions use actual local files and the real controller. They
establish software behavior, not real game detection under every Windows access
policy or successful inference/unloading of a physically installed Ollama model.
Those remain manual acceptance requirements.

## Русский

### Реализованные возможности

Игровые профили хранятся в `games.json` рядом с обычными настройками. Автоопределение
**выключено по умолчанию**, как и выгрузка моделей. На странице «Игры» можно
добавлять, выбирать, изменять и удалять игры: имена файлов разделяются точкой с
запятой, а выгрузка требует отдельного флажка для каждой игры. Новые записи
используют игровой режим. Пользователь задаёт точные имена исполняемых файлов,
режим `Smart`, `Gaming`, `Maximum AI` или `Eco`, выгрузку модели и приоритет от -100
до 100. Регистр имён не учитывается. Пути, шаблоны и предположения о неизвестных
играх не используются. При равных приоритетах действует порядок профилей.

Проверяются реальные процессы через psutil в фоновом задании. Если имена некоторых
процессов недоступны, отсутствие совпадения не считается доказательством закрытия
игры: сохраняется последний подтверждённый игровой режим. Для уже обнаруженных
игровых процессов дополнительно проверяется `is_running()` psutil с учётом
повторного использования PID. Так можно подтвердить закрытие известной игры,
даже если имена посторонних системных процессов недоступны. Ошибка проверки не
считается закрытием. После подтверждённого завершения, полного опроса без
совпадений или отключения обнаружения возвращается выбранный пользователем режим.
Процессы не запускаются и не завершаются; настройки Windows и FPS не изменяются.

Выгрузка использует официальный `POST /api/generate` с выбранной моделью, пустым
запросом и `keep_alive:0`. Успех подтверждается `done:true` и `done_reason:"unload"`; поля модели и ответа
дополнительно проверяются, если сервер их вернул. Поддерживаются чтение `GET /api/ps` и явная
загрузка через пустой запрос с ограниченным временем удержания. Файлы моделей не
удаляются, модели не скачиваются, процесс Ollama не завершается.

Автовыгрузка возможна только для модели, которой успешно пользовалась NEXUS, после
явного включения функции и подтверждения запуска настроенной игры. Во время
запроса выгрузка откладывается. Ошибки не вызывают непрерывных повторов.

**Память модели общая для всех клиентов Ollama.** Другое приложение, использующее
ту же модель, может быть затронуто. Поэтому согласие на функцию должно явно
объяснять этот эффект; список загруженных моделей не считается списком моделей,
принадлежащих NEXUS.

При закрытии игры возвращается исходный режим, но загрузка модели автоматически
не запускается. Следующий явный запрос чата восстанавливает модель штатным API.
Явное действие восстановления может предварительно загрузить её. Для текущей
игры оно приостанавливает повторную автовыгрузку до смены игры или ручной выгрузки.

Настройки записываются атомарно. Повреждённые файлы сохраняются, а обнаружение
остаётся выключенным. Сетевые операции и опрос процессов должны выполняться в
рабочих потоках; Qt-интерфейс не должен ожидать их синхронно.

Документация API приведена выше. Автотесты проверяют протокол, ошибки, переходы
режимов и сохранение файлов. Работа с установленной моделью Ollama и реальными
играми на физическом компьютере Windows остаётся непроверенной вручную; успешные
тесты не выдаются за такую проверку.
