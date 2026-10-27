# NEXUS AI v1.0 — Game Guard

The original PR #4 backend API in `game_lifecycle.py` is preserved with its tests.
The desktop now uses the richer persistent `gaming.py` / `lifecycle.py` services
through `ui/game_center.py`. See [the bilingual implementation and safety
contract](gaming.md) for details.

The existing Gaming page supports adding, editing and removing configured games.
Detection and per-game model unloading require explicit opt-in. Real process names
are scanned in a background worker. Confirmed games select Gaming mode; after the
known session ends, the selected base performance mode returns. Users can change
that base mode during gaming without changing the currently effective game policy.

Only a model successfully used by NEXUS is eligible for automatic unloading.
Ollama's supported API runs outside the UI thread and never kills processes,
deletes models or adopts unrelated loaded models. Ollama residency is server-wide:
other clients using the same model may be affected, as explained in the UI.
Models load again only on explicit chat or restoration requests.

## Русский

Исходный API из PR #4 и его тесты сохранены. На странице «Игры» теперь работают
добавление, изменение и удаление настроенных игр. Обнаружение процессов и выгрузка
моделей включаются явно. Запуск подтверждённой игры включает игровой режим;
после завершения известного сеанса возвращается выбранный пользователем профиль.

Выгружается только модель, которой успешно пользовалась NEXUS. Сеть, чтение
процессов и файлов выполняются в рабочих потоках. Процессы не завершаются,
модели не удаляются. Память одной модели Ollama общая для клиентов сервера,
поэтому согласие на выгрузку предупреждает о влиянии на другие приложения.
Загрузка модели происходит по явному запросу чата или восстановления.

Tests use local fixtures for process and API behavior. Real game sessions and
GPU-memory recovery on a physical Windows/Ollama installation remain manual
acceptance requirements; simulated tests do not establish hardware validation.
