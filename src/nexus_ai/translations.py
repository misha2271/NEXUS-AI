"""Complete Russian catalog; English is the canonical source catalog.

Placeholders are identical in both languages. Brand names and protocol/hardware
identifiers are intentionally unchanged. Additions are checked by localization tests.
"""

RU = {
    "Settings": "Настройки",
    "Ollama settings": "Настройки Ollama",
    "Server URL": "Адрес сервера",
    "Ollama server URL": "Адрес сервера Ollama",
    "Use an existing Ollama server, such as http://127.0.0.1:11434.": (
        "Укажите адрес работающего сервера Ollama, например http://127.0.0.1:11434."
    ),
    "Language": "Язык",
    "Language changes are saved immediately. Other settings use Save.": (
        "Язык меняется и сохраняется сразу. Для остальных настроек нажмите «Сохранить»."
    ),
    "Save": "Сохранить",
    "Cancel": "Отмена",
    "&Save": "&Сохранить",
    "&Cancel": "&Отмена",
    "PROFILE": "ПРОФИЛЬ",
    "Performance profile": "Профиль производительности",
    "Smart": "Умный",
    "Maximum AI": "Максимум ИИ",
    "Gaming": "Игровой",
    "Eco": "Эко",
    "Profiles apply to the next Ollama request, not OS settings.": (
        "Профиль применяется к следующему запросу Ollama и не меняет настройки ОС."
    ),
    "Larger context and CPU budget; Ollama selects GPU offload.": (
        "Увеличенные контекст и ресурс ЦП; Ollama выбирает использование ГП."
    ),
    "CPU-only inference with up to two threads; unload after each response.": (
        "Вычисления только на ЦП, до двух потоков; выгрузка модели после каждого ответа."
    ),
    ("One CPU thread, smaller context, slower monitoring; unload after each response."): (
        "Один поток ЦП, меньший контекст, редкий опрос; выгрузка модели после каждого ответа."
    ),
    "Resource pressure detected: reduced thread/context budget.": (
        "Высокая нагрузка: уменьшены число потоков и размер контекста."
    ),
    "Balanced CPU budget; Ollama selects GPU offload.": (
        "Сбалансированная нагрузка ЦП; Ollama выбирает использование ГП."
    ),
    "Unknown performance profile: {profile}": ("Неизвестный профиль производительности: {profile}"),
    "Overview": "Обзор",
    "Assistant": "Ассистент",
    "RGB Studio": "Студия RGB",
    "Logitech G560": "Logitech G560",
    "Gamepad Lab": "Геймпады",
    "SSD Health": "Состояние SSD",
    "Update Center": "Центр обновлений",
    "WORKSPACE / OVERVIEW": "РАБОЧЕЕ ПРОСТРАНСТВО / ОБЗОР",
    "WORKSPACE / {page}": "РАБОЧЕЕ ПРОСТРАНСТВО / {page}",
    "Navigate to {title}": "Открыть: {title}",
    "PERSONAL SYSTEM WORKSPACE": "ЛИЧНОЕ ПРОСТРАНСТВО СИСТЕМЫ",
    "LOCAL BY DESIGN": "ЛОКАЛЬНАЯ РАБОТА",
    "RGB & fan writes locked": "Управление RGB и вентиляторами заблокировано",
    "System overview": "Обзор системы",
    "Live host signals. No simulated metrics.": (
        "Реальные показания системы. Без имитации данных."
    ),
    "CPU / UTILIZATION": "ЦП / ЗАГРУЗКА",
    "RAM / SYSTEM MEMORY": "ОЗУ / СИСТЕМНАЯ ПАМЯТЬ",
    "GPU / NVIDIA UTILIZATION": "ГП / ЗАГРУЗКА NVIDIA",
    "VRAM / DEVICE MEMORY": "ВИДЕОПАМЯТЬ / ИСПОЛЬЗОВАНИЕ",
    "Waiting for telemetry…": "Ожидание показаний…",
    "History begins with this session · up to 300 samples / 10 min": (
        "История текущего сеанса · до 300 измерений за 10 минут"
    ),
    ("{count} real samples · up to 300 samples / 10 min · GPU lines follow device index"): (
        "Реальных измерений: {count} · до 300 за 10 "
        "минут · линии ГП соответствуют индексам "
        "устройств"
    ),
    "CPU utilization / %": "Загрузка ЦП / %",
    "Memory usage / %": "Использование ОЗУ / %",
    "GPU utilization / % · all devices": "Загрузка ГП / % · все устройства",
    "VRAM usage / % · all devices": "Видеопамять / % · все устройства",
    "Host temperatures / °C": "Датчики системы / °C",
    "GPU temperatures / °C": "Температура ГП / °C",
    "{title} historical chart": "{title}: график истории",
    "No readings available": "Нет доступных показаний",
    "Collecting history…": "Накопление истории…",
    "{duration:.0f}s captured · gaps = unavailable": (
        "Записано: {duration:.0f} с · пропуски — нет данных"
    ),
    "Historical series: {series}": "История показаний: {series}",
    "No sensor readings available": "Нет доступных показаний датчиков",
    "TEMPERATURE SENSORS": "ДАТЧИКИ ТЕМПЕРАТУРЫ",
    "Waiting for real sensor readings…": "Ожидание реальных показаний датчиков…",
    "Fan controls · no validated SDK": "Управление вентиляторами · нет проверенного SDK",
    "Checking optional NVIDIA telemetry…": "Проверка доступности показаний NVIDIA…",
    "GPU unavailable": "ГП недоступен",
    "VRAM unavailable": "Видеопамять недоступна",
    "First reported GPU; all devices are shown below and in charts.": (
        "Первый обнаруженный ГП; все устройства показаны ниже и на графиках."
    ),
    "Memory of first reported GPU; all devices are charted.": (
        "Память первого обнаруженного ГП; все устройства представлены на графиках."
    ),
    ("No host sensor data. Windows CPU temperatures require a supported sensor provider."): (
        "Нет показаний датчиков системы. Для "
        "температуры ЦП в Windows нужен "
        "поддерживаемый источник данных."
    ),
    "Unavailable": "Недоступно",
    "{value:.1f} GiB": "{value:.1f} ГиБ",
    "{value:.1f}%": "{value:.1f} %",
    "{value:.0f}% utilization": "Загрузка: {value:.0f} %",
    "Utilization unavailable": "Загрузка недоступна",
    "Temperature unavailable": "Температура недоступна",
    "Temperature readings unavailable": "Показания температуры недоступны",
    "CPU telemetry unavailable": "Показания ЦП недоступны",
    "RAM telemetry unavailable": "Показания ОЗУ недоступны",
    "CPU telemetry available": "Показания ЦП доступны",
    "RAM telemetry available": "Показания ОЗУ доступны",
    "Collecting first CPU sample": "Сбор первого измерения ЦП",
    "CPU telemetry unavailable: {error}": "Показания ЦП недоступны: {error}",
    "RAM telemetry unavailable: {error}": "Показания ОЗУ недоступны: {error}",
    "Telemetry unavailable: {error}": "Показания недоступны: {error}",
    "Temperature sensors unavailable on this platform": (
        "Датчики температуры недоступны на этой платформе"
    ),
    "Host temperature sensors unavailable on this platform": (
        "Датчики температуры системы недоступны на этой платформе"
    ),
    "Host temperature sensors available": "Датчики температуры системы доступны",
    "No readable host temperature sensors": "Нет доступных для чтения датчиков температуры",
    "Host temperature sensors unavailable: {error}": (
        "Датчики температуры системы недоступны: {error}"
    ),
    "Sensor {index}": "Датчик {index}",
    "NVIDIA telemetry not initialized": "Сбор показаний NVIDIA не запущен",
    "NVIDIA telemetry unavailable: optional nvidia-ml-py package is not installed": (
        "Показания NVIDIA недоступны: дополнительный пакет nvidia-ml-py не установлен"
    ),
    "NVIDIA telemetry unavailable: {error}": "Показания NVIDIA недоступны: {error}",
    "NVIDIA telemetry unavailable (NVML/driver): {error}": (
        "Показания NVIDIA недоступны (NVML/драйвер): {error}"
    ),
    "NVIDIA telemetry unavailable: no NVIDIA devices detected": (
        "Показания NVIDIA недоступны: устройства NVIDIA не обнаружены"
    ),
    "NVIDIA telemetry available ({count} device(s))": (
        "Показания NVIDIA доступны (устройств: {count})"
    ),
    "NVIDIA telemetry {state}: {errors}": "Показания NVIDIA {state}: {errors}",
    "partial": "доступны частично",
    "unavailable": "недоступны",
    "GPU {index}: {error}": "ГП {index}: {error}",
    "GPU {index} utilization: {error}": "ГП {index}, загрузка: {error}",
    "GPU {index} memory: {error}": "ГП {index}, память: {error}",
    "GPU {index} temperature: {error}": "ГП {index}, температура: {error}",
    "{utilization}\nVRAM: {used} / {total}\n{temperature}": (
        "{utilization}\nВидеопамять: {used} / {total}\n{temperature}"
    ),
    "GPU {index} · {name}": "ГП {index} · {name}",
    "Your local assistant": "Ваш локальный ассистент",
    "Streamed from your Ollama server. Your model, your workspace.": (
        "Потоковые ответы с вашего сервера Ollama. Ваша модель и ваше пространство."
    ),
    "MODEL": "МОДЕЛЬ",
    "Installed Ollama model": "Установленная модель Ollama",
    "Refresh models": "Обновить модели",
    "Connect to Ollama to discover installed models.": (
        "Подключитесь к Ollama для поиска установленных моделей."
    ),
    (
        "A clear space to think.\n\nChoose an installed"
        " model, then start a conversation.\nHistory "
        "stays in this session; prompts go to your "
        "configured Ollama server."
    ): (
        "Пространство для ваших идей.\n\nВыберите "
        "установленную модель и начните разговор.\n"
        "История хранится только в этом сеансе; "
        "запросы отправляются на указанный сервер "
        "Ollama."
    ),
    "Chat transcript": "История разговора",
    "Message": "Сообщение",
    "Ask NEXUS…  (Ctrl+Enter to send)": "Спросите NEXUS…  (Ctrl+Enter — отправить)",
    "Clear chat": "Очистить чат",
    "Copy": "Копировать",
    "Stop": "Остановить",
    "Send": "Отправить",
    "Connecting to Ollama…": "Подключение к Ollama…",
    "Generating…": "Формирование ответа…",
    "You\n{prompt}\n\nNEXUS · {model}\n": "Вы\n{prompt}\n\nNEXUS · {model}\n",
    "{model} · {size} download size": "{model} · размер загрузки: {size}",
    "Ollama connected · {count} installed model(s)": (
        "Ollama подключена · установлено моделей: {count}"
    ),
    "No installed models. Run 'ollama pull llama3.2:3b', then refresh models.": (
        "Нет установленных моделей. Выполните 'ollama pull llama3.2:3b' и обновите список."
    ),
    "\n[Generation stopped; partial reply excluded from context.]\n": (
        "\n[Формирование остановлено; неполный ответ исключён из контекста.]\n"
    ),
    "Stopped. Ready for another message.": "Остановлено. Можно отправить новое сообщение.",
    "Ready · reply complete": "Готово · ответ получен",
    "[Ollama completed without answer text.]\n": ("[Ollama завершила запрос без текста ответа.]\n"),
    "No answer text returned. Try another model or prompt.": (
        "Ответ не содержит текста. Попробуйте другую модель или запрос."
    ),
    "\n[Reply failed: {error}]\n": "\n[Ошибка ответа: {error}]\n",
    "Stopping… waiting for the next response chunk or network timeout.": (
        "Остановка… ожидание следующего фрагмента ответа или тайм-аута сети."
    ),
    "Closing… waiting for background work to finish.": (
        "Закрытие… ожидание завершения фоновых задач."
    ),
    "{message} Network reads can take up to 60 seconds.": (
        "{message} Ожидание данных сети может занять до 60 секунд."
    ),
    "Settings were not saved: {error}": "Настройки не сохранены: {error}",
    "DEVICE WORKSPACE": "ПРОСТРАНСТВО УСТРОЙСТВА",
    "NOT CONNECTED · NO VALIDATED PROVIDER": ("НЕ ПОДКЛЮЧЕНО · НЕТ ПРОВЕРЕННОГО ИСТОЧНИКА ДАННЫХ"),
    "Hardware controls remain locked until a supported SDK is validated.": (
        "Управление оборудованием заблокировано до проверки поддерживаемого SDK."
    ),
    "{action} · unavailable": "{action} · недоступно",
    "Requires an implemented, supported and hardware-validated provider": (
        "Нужен реализованный и проверенный на оборудовании поддерживаемый модуль"
    ),
    "Use existing Gaming inference profile": "Применить игровой профиль вычислений",
    "Installed application  /  {version}": "Установленная версия  /  {version}",
    "A quieter inference budget while you play.": ("Снижение нагрузки вычислений во время игры."),
    (
        "The existing Gaming profile changes Ollama "
        "request options only. Game detection, FPS "
        "capture, OS tuning, and fan control are not "
        "implemented."
    ): (
        "Игровой профиль меняет только параметры "
        "запросов Ollama. Поиск игр, измерение FPS, "
        "настройка ОС и управление вентиляторами не "
        "реализованы."
    ),
    "Fan control": "Управление вентиляторами",
    "A future home for supported lighting devices.": (
        "Будущее пространство для поддерживаемых устройств подсветки."
    ),
    (
        "No RGB SDK is connected or validated. Device"
        " discovery and lighting writes are "
        "unavailable; no HID packets or device "
        "commands are sent."
    ): (
        "SDK для RGB не подключён и не проверен. "
        "Поиск устройств и изменение подсветки "
        "недоступны; HID-пакеты и команды устройствам"
        " не отправляются."
    ),
    "Apply lighting": "Применить подсветку",
    "Speaker lighting and device capabilities.": ("Подсветка колонок и возможности устройства."),
    (
        "Requires a supported Logitech SDK, a "
        "connected G560, and physical-device "
        "validation. No speaker, lighting, audio, or "
        "firmware integration is implemented."
    ): (
        "Нужны поддерживаемый SDK Logitech, "
        "подключённая G560 и проверка на реальном "
        "устройстве. Управление колонками, "
        "подсветкой, звуком и прошивкой не "
        "реализовано."
    ),
    "Apply speaker RGB": "Применить подсветку колонок",
    "A future workspace for controller diagnostics.": (
        "Будущее пространство для диагностики контроллеров."
    ),
    (
        "No controller backend is connected. Input "
        "capture, rumble, calibration, and firmware "
        "operations require a validated provider."
    ): (
        "Модуль контроллеров не подключён. Чтение "
        "ввода, вибрация, калибровка и работа с "
        "прошивкой требуют проверенного модуля."
    ),
    "Test rumble": "Проверить вибрацию",
    "Health information from supported storage providers.": (
        "Сведения о состоянии от поддерживаемых модулей накопителей."
    ),
    (
        "No SMART/NVMe health provider is connected. "
        "Health, endurance, and drive temperature are"
        " unavailable. Filesystem free space is not a"
        " drive health measurement."
    ): (
        "Источник состояния SMART/NVMe не подключён. "
        "Состояние, ресурс и температура накопителя "
        "недоступны. Свободное место не является "
        "показателем здоровья накопителя."
    ),
    "Read SMART": "Прочитать SMART",
    "Installed version and future update verification.": (
        "Установленная версия и будущая проверка обновлений."
    ),
    (
        "Automatic update checks and installers are "
        "not implemented. A future provider must "
        "verify signed metadata and artifacts before "
        "offering an update. Nothing is downloaded or"
        " installed automatically."
    ): (
        "Автопроверка обновлений и установщики не "
        "реализованы. Перед предложением обновления "
        "будущий модуль должен проверять подпись "
        "метаданных и файлов. Ничего не скачивается и"
        " не устанавливается автоматически."
    ),
    "Check for updates": "Проверить обновления",
    "Install update": "Установить обновление",
    "No validated hardware provider connected": ("Проверенный модуль оборудования не подключён"),
    "Ollama URL must be text.": "Адрес Ollama должен быть строкой.",
    "Ollama URL must not contain whitespace or control characters.": (
        "Адрес Ollama не должен содержать пробельные или управляющие символы."
    ),
    "Ollama URL must not contain backslashes.": (
        "Адрес Ollama не должен содержать обратные косые черты."
    ),
    "Ollama URL contains an invalid hostname or port.": (
        "В адресе Ollama указано неверное имя узла или порт."
    ),
    "Ollama URL must be an HTTP or HTTPS URL with a hostname.": (
        "Адрес Ollama должен содержать HTTP или HTTPS и имя узла."
    ),
    "Ollama URL port must be between 1 and 65535.": (
        "Порт Ollama должен находиться в диапазоне от 1 до 65535."
    ),
    "Ollama URL must not contain embedded credentials.": (
        "Адрес Ollama не должен содержать учётные данные."
    ),
    "Ollama URL must not contain a query or fragment.": (
        "Адрес Ollama не должен содержать параметры запроса или фрагмент."
    ),
    "Model name must be text.": "Имя модели должно быть строкой.",
    "Model name must not contain control characters.": (
        "Имя модели не должно содержать управляющие символы."
    ),
    "Choose a supported performance profile.": (
        "Выберите поддерживаемый профиль производительности."
    ),
    "Choose Russian or English.": "Выберите русский или английский язык.",
    "Settings could not be read; defaults are in use. The file was preserved.": (
        "Не удалось прочитать настройки; используются"
        " значения по умолчанию. Файл сохранён без "
        "изменений."
    ),
    "Settings must be a JSON object; defaults are in use. The file was preserved.": (
        "Настройки должны быть объектом JSON; "
        "используются значения по умолчанию. Файл "
        "сохранён без изменений."
    ),
    "Invalid settings reset to defaults: {fields}. The file was preserved.": (
        "Некорректные настройки сброшены: {fields}. Файл сохранён без изменений."
    ),
    "Ollama URL must be an HTTP or HTTPS URL.": (
        "Адрес Ollama должен использовать HTTP или HTTPS."
    ),
    "Ollama URL needs an HTTP(S) host without credentials, query, or fragment.": (
        "Для Ollama нужен адрес узла HTTP(S) без учётных данных, параметров запроса и фрагмента."
    ),
    "Ollama returned an invalid model list (expected 'models').": (
        "Ollama вернула неверный список моделей (ожидалось поле 'models')."
    ),
    "Ollama returned an invalid model entry.": "Ollama вернула неверные сведения о модели.",
    "Ollama returned a model without a valid name.": (
        "Ollama вернула модель без допустимого имени."
    ),
    "Ollama returned an invalid model size.": "Ollama вернула неверный размер модели.",
    "Select an installed model before sending a message.": (
        "Перед отправкой сообщения выберите установленную модель."
    ),
    "Ollama returned an invalid 'done' marker.": ("Ollama вернула неверное значение поля 'done'."),
    "Ollama returned an invalid chat message.": "Ollama вернула неверное сообщение чата.",
    "Ollama returned a chat chunk without a message.": (
        "Ollama вернула фрагмент ответа без сообщения."
    ),
    "Ollama disconnected before completing the reply. Try again.": (
        "Ollama отключилась до завершения ответа. Повторите запрос."
    ),
    "Ollama returned malformed JSON. Check the server URL.": (
        "Ollama вернула некорректный JSON. Проверьте адрес сервера."
    ),
    "Ollama returned an invalid response (expected a JSON object).": (
        "Ollama вернула неверный ответ (ожидался объект JSON)."
    ),
    (
        "Model '{model}' is unavailable. Install it "
        "with 'ollama pull {model}', then refresh the"
        " model list. {detail}"
    ): (
        "Модель '{model}' недоступна. Установите её "
        "командой 'ollama pull {model}' и обновите "
        "список моделей. {detail}"
    ),
    "Ollama HTTP {status}.": "Ошибка HTTP Ollama: {status}.",
    " Check the server URL; it must point to an Ollama server.": (
        " Проверьте адрес: он должен указывать на сервер Ollama."
    ),
    (
        "Ollama request timed out. The model may "
        "still be loading; check Ollama and try "
        "again, or choose a smaller model."
    ): (
        "Время ожидания Ollama истекло. Возможно, "
        "модель ещё загружается; проверьте Ollama и "
        "повторите запрос или выберите меньшую "
        "модель."
    ),
    "Cannot reach Ollama. Start it with 'ollama serve' and check the server URL.": (
        "Не удаётся подключиться к Ollama. Запустите "
        "её командой 'ollama serve' и проверьте адрес"
        " сервера."
    ),
    "Unknown server error": "Неизвестная ошибка сервера",
    " Install the model with 'ollama pull {model}' and refresh models.": (
        " Установите модель командой 'ollama pull {model}' и обновите список."
    ),
    "Telemetry collector is closed": "Сборщик показаний закрыт",
    "Wait for the current request before changing the server URL.": (
        "Дождитесь завершения текущего запроса перед изменением адреса сервера."
    ),
    "Undo": "Отменить",
    "Redo": "Повторить",
    "Cut": "Вырезать",
    "Paste": "Вставить",
    "Delete": "Удалить",
    "Select All": "Выделить всё",
    "Select all": "Выделить всё",
    "Ollama: {detail}": "Ollama: {detail}",
    "Ollama request failed: {error}": "Ошибка запроса Ollama: {error}",
    "GPU {index}": "ГП {index}",
    "VRAM {index}": "Видеопамять {index}",
    "GPU {index} temperature": "Температура ГП {index}",
}

# Standard Qt edit-menu mnemonics remain active in each language.
RU.update(
    {
        "&Undo": "&Отменить",
        "&Redo": "&Повторить",
        "Cu&t": "Вы&резать",
        "&Cut": "Вы&резать",
        "&Copy": "&Копировать",
        "&Paste": "Вст&авить",
        "&Delete": "&Удалить",
        "Select &All": "Выделить &всё",
        "&Select All": "Выделить &всё",
    }
)

RU.update(
    {
        "Scroll here": "Прокрутить сюда",
        "Top": "В начало",
        "Bottom": "В конец",
        "Page up": "На страницу вверх",
        "Page down": "На страницу вниз",
        "Scroll up": "Прокрутить вверх",
        "Scroll down": "Прокрутить вниз",
        "Left edge": "К левому краю",
        "Right edge": "К правому краю",
        "Page left": "На страницу влево",
        "Page right": "На страницу вправо",
        "Scroll left": "Прокрутить влево",
        "Scroll right": "Прокрутить вправо",
    }
)

# v1 services: storage and protocol errors are translated at the UI boundary.
RU.update(
    {
        "A conversation message exceeds the configured text limit.": (
            "Сообщение превышает допустимый объём текста."
        ),
        "Choose a valid conversation identifier.": "Укажите допустимый идентификатор беседы.",
        "Choose a valid conversation list limit.": "Укажите допустимое ограничение числа бесед.",
        "Choose a valid conversation revision.": "Укажите допустимую версию беседы.",
        "Conversation messages must be a list of chat messages.": (
            "Сообщения беседы должны быть списком сообщений чата."
        ),
        "Conversation messages must contain user or assistant text.": (
            "Сообщения беседы должны содержать текст пользователя или ассистента."
        ),
        "Conversation messages must contain valid Unicode text.": (
            "Сообщения беседы должны содержать корректный текст Unicode."
        ),
        "Conversation messages need only role and content fields.": (
            "В сообщениях беседы допускаются только поля роли и текста."
        ),
        "Conversation storage exceeds the configured size limit.": (
            "Хранилище бесед превышает допустимый размер."
        ),
        "Conversation storage failed; existing data was preserved: {error}": (
            "Ошибка хранилища бесед; существующие данные сохранены: {error}"
        ),
        "Conversation storage has an unsupported schema; the file was preserved.": (
            "Формат хранилища бесед не поддерживается; файл сохранён."
        ),
        "Conversation storage is full; delete an old chat first.": (
            "Хранилище бесед заполнено; сначала удалите старую беседу."
        ),
        "Conversation storage must not be a symbolic link.": (
            "Хранилище бесед не должно быть символической ссылкой."
        ),
        "Conversation titles must be text of at most 200 characters.": (
            "Название беседы должно содержать не более 200 символов."
        ),
        "Conversation titles must contain valid Unicode text.": (
            "Название беседы должно содержать корректный текст Unicode."
        ),
        "Stored conversation data is invalid; the file was preserved.": (
            "Сохранённые данные беседы некорректны; файл сохранён."
        ),
        "This conversation changed in another operation; reload it before saving.": (
            "Беседа изменена другой операцией; загрузите её заново перед сохранением."
        ),
        "This conversation exceeds the configured message limit.": (
            "Беседа превышает допустимое число сообщений."
        ),
        "This conversation exceeds the configured text limit.": (
            "Беседа превышает допустимый объём текста."
        ),
        "This conversation no longer exists.": "Эта беседа больше не существует.",
        "Add executable names to enable game detection.": (
            "Добавьте имена исполняемых файлов для обнаружения игр."
        ),
        "At most 100 game profiles are supported.": "Поддерживается не более 100 игровых профилей.",
        "Automatic game detection is disabled.": "Автоматическое обнаружение игр отключено.",
        "Game detected: {game}": "Обнаружена игра: {game}",
        "Game detection configuration is invalid.": "Настройки обнаружения игр некорректны.",
        "Game profile configuration is too large.": "Настройки игровых профилей слишком велики.",
        "Game profile is invalid.": "Игровой профиль некорректен.",
        "Game profile mode or unload preference is invalid.": (
            "Режим игрового профиля или настройка выгрузки некорректны."
        ),
        "Game profile names must be unique.": "Названия игровых профилей должны быть уникальными.",
        "Game profile needs a valid name.": "Укажите допустимое название игрового профиля.",
        "Game profile priority must be between -100 and 100.": (
            "Приоритет игрового профиля должен быть от −100 до 100."
        ),
        ("Game profiles could not be read. Detection is disabled; the file was preserved."): (
            "Не удалось прочитать игровые профили. Обнаружение отключено; файл сохранён."
        ),
        "No configured game process is running.": "Ни одна из настроенных игр не запущена.",
        "Process detection is incomplete; some process names are inaccessible.": (
            "Обнаружение процессов неполное: некоторые имена процессов недоступны."
        ),
        "Specify between 1 and 32 executable names per game profile.": (
            "Укажите от 1 до 32 имён исполняемых файлов для игрового профиля."
        ),
        "Use exact executable basenames, not paths or wildcards.": (
            "Укажите точные имена исполняемых файлов без путей и подстановочных знаков."
        ),
        (
            "A G560 name match does not validate Logitech LED SDK support. Speaker RGB, "
            "audio and firmware controls remain disabled."
        ): (
            "Совпадение имени G560 не подтверждает поддержку Logitech LED SDK. Управление"
            " подсветкой, звуком и прошивкой колонок остаётся отключённым."
        ),
        "Cooling": "Охлаждение",
        "Inconsistent Windows fan inventory state.": (
            "Состояние списка вентиляторов Windows противоречиво."
        ),
        "Invalid Windows baseboard entry.": "Некорректная запись о системной плате Windows.",
        "Invalid Windows device entry.": "Некорректная запись об устройстве Windows.",
        "Invalid Windows device hardware identifiers.": (
            "Некорректные аппаратные идентификаторы устройства Windows."
        ),
        "Invalid Windows fan entry.": "Некорректная запись о вентиляторе Windows.",
        "Invalid Windows fan inventory state.": (
            "Некорректное состояние списка вентиляторов Windows."
        ),
        "Invalid Windows hardware list: {field}.": (
            "Некорректный список оборудования Windows: {field}."
        ),
        (
            "MSI board identity is detection evidence only. Mystic Light compatibility "
            "and the vendor SDK are not validated; RGB writes remain disabled."
        ): (
            "Обнаружение платы MSI подтверждает только её наличие. Совместимость Mystic "
            "Light и SDK производителя не проверена; управление RGB остаётся отключённым."
        ),
        (
            "Read-only Windows inventory collected. Candidate matches do not enable "
            "hardware controls."
        ): (
            "Сведения об оборудовании Windows получены без изменения устройств. "
            "Совпадения имён не включают управление оборудованием."
        ),
        "Unsupported Windows diagnostic response.": "Неподдерживаемый ответ диагностики Windows.",
        (
            "Win32_Fan inventory does not prove actual RPM, temperature or writable "
            "control. Cooling controls remain disabled without a supported, physically "
            "validated provider."
        ): (
            "Список Win32_Fan не подтверждает доступ к оборотам, температуре или "
            "управлению. Управление охлаждением отключено до проверки поддерживаемого "
            "поставщика на реальном оборудовании."
        ),
        "Windows hardware inventory is unavailable on this platform.": (
            "Сведения об оборудовании Windows недоступны на этой платформе."
        ),
        (
            "Windows hardware query unavailable. No SDK was loaded and no device commands"
            " were sent."
        ): (
            "Запрос оборудования Windows недоступен. SDK не загружался, команды "
            "устройствам не отправлялись."
        ),
        (
            "Xbox-family PnP names do not prove Elite Series 2 identity or paddle "
            "support. GameInput/XInput integration and rumble remain unvalidated and "
            "disabled."
        ): (
            "Имена PnP семейства Xbox не подтверждают модель Elite Series 2 или поддержку"
            " лепестков. Интеграция GameInput/XInput и вибрация не проверены и отключены."
        ),
        "Game detection is incomplete; keeping the current game mode.": (
            "Обнаружение игр неполное; текущий игровой режим сохранён."
        ),
        "Game mode: {game}. Models restore only when requested.": (
            "Игровой режим: {game}. Модели загружаются только по запросу."
        ),
        ("Model restoration was requested; automatic unloading is paused for this game."): (
            "Запрошена загрузка модели; автоматическая выгрузка приостановлена для этой игры."
        ),
        (
            "Model unloading failed; automatic retry is paused until a new request or "
            "game transition."
        ): (
            "Не удалось выгрузить модель; автоматический повтор приостановлен до нового "
            "запроса или смены состояния игры."
        ),
        "Model unloading is deferred until the active request finishes.": (
            "Выгрузка модели отложена до завершения текущего запроса."
        ),
        "Using the selected mode. Models restore only when requested.": (
            "Используется выбранный режим. Модели загружаются только по запросу."
        ),
        "Model retention must be positive and at most 24 hours.": (
            "Время удержания модели должно быть положительным и не превышать 24 часов."
        ),
        "Ollama did not acknowledge the requested model lifecycle operation.": (
            "Ollama не подтвердила запрошенную операцию с моделью."
        ),
        "Ollama returned an invalid running-model entry.": (
            "Ollama вернула некорректные сведения о загруженной модели."
        ),
        "Ollama returned an invalid running-model list.": (
            "Ollama вернула некорректный список загруженных моделей."
        ),
        "Select a valid installed model for lifecycle operations.": (
            "Выберите допустимую установленную модель для операций загрузки и выгрузки."
        ),
        "A bounded request length is required.": "Необходимо указать ограниченную длину запроса.",
        "A configured TLS certificate or key file is missing.": (
            "Указанный файл сертификата TLS или ключа не найден."
        ),
        "A remote-control allowed hostname is invalid.": (
            "Разрешённое имя узла удалённого управления некорректно."
        ),
        "Bind remote control to a specific local IP address.": (
            "Укажите конкретный локальный IP-адрес для удалённого управления."
        ),
        "Cross-origin remote requests are not allowed.": (
            "Удалённые запросы с другого источника запрещены."
        ),
        "LAN remote control requires a trusted TLS certificate and private key.": (
            "Для удалённого управления по локальной сети необходимы доверенный сертификат"
            " TLS и закрытый ключ."
        ),
        "Remote authentication failed.": "Ошибка проверки подлинности удалённого подключения.",
        "Remote command processing is stopped.": "Обработка удалённых команд остановлена.",
        "Remote commands require JSON.": "Для удалённых команд требуется JSON.",
        "Remote control is already running.": "Удалённое управление уже запущено.",
        "Remote control is disabled. Enable it explicitly to start.": (
            "Удалённое управление отключено. Включите его явно для запуска."
        ),
        "Remote control must be explicitly enabled.": (
            "Удалённое управление необходимо включить явно."
        ),
        "Remote control requires a token containing at least 32 random bytes.": (
            "Для удалённого управления требуется токен не менее чем из 32 случайных байтов."
        ),
        "Supply both the TLS certificate and its private key.": (
            "Укажите сертификат TLS и его закрытый ключ."
        ),
        "The TLS certificate and key could not be loaded.": (
            "Не удалось загрузить сертификат TLS и ключ."
        ),
        "The remote command could not be completed.": "Не удалось выполнить удалённую команду.",
        "The remote command queue is full.": "Очередь удалённых команд заполнена.",
        "The remote command timed out. Check status before retrying.": (
            "Время ожидания удалённой команды истекло. Проверьте состояние перед повтором."
        ),
        "The remote connection or rate limit is invalid.": (
            "Ограничение подключений или частоты удалённых запросов некорректно."
        ),
        "The remote endpoint was not found.": "Адрес удалённого API не найден.",
        "The remote request body is too large.": "Тело удалённого запроса слишком велико.",
        "The remote request nonce is invalid or was already used.": (
            "Одноразовый идентификатор удалённого запроса некорректен или уже использован."
        ),
        "The remote request timeout must be between 1 and 30 seconds.": (
            "Время ожидания удалённого запроса должно быть от 1 до 30 секунд."
        ),
        "The remote request was rejected.": "Удалённый запрос отклонён.",
        "The remote token is invalid.": "Токен удалённого доступа некорректен.",
        "The remote-control port must be between 0 and 65535.": (
            "Порт удалённого управления должен быть от 0 до 65535."
        ),
        "This remote command does not accept parameters.": (
            "Эта удалённая команда не принимает параметры."
        ),
        "This remote command is not approved.": "Эта удалённая команда не разрешена.",
        "This remote hostname is not approved.": "Это имя узла удалённого доступа не разрешено.",
        "This remote method is not allowed.": "Этот метод удалённого доступа запрещён.",
        "Too many remote requests. Try again later.": (
            "Слишком много удалённых запросов. Повторите попытку позже."
        ),
        "Use GET for remote status.": "Для получения удалённого состояния используйте GET.",
        "Use POST for remote commands.": "Для удалённых команд используйте POST.",
        "Wildcard and multicast remote-control bindings are not allowed.": (
            "Обобщённые и многоадресные привязки удалённого управления запрещены."
        ),
        "Invalid Windows counter error code.": "Некорректный код ошибки счётчика Windows.",
        "Invalid Windows diagnostic field: {field}.": (
            "Некорректное поле диагностики Windows: {field}."
        ),
        "Invalid Windows disk entry.": "Некорректная запись о диске Windows.",
        "Invalid Windows disk list.": "Некорректный список дисков Windows.",
        "Invalid Windows disk operational status.": "Некорректное рабочее состояние диска Windows.",
        "Invalid or duplicate Windows disk identifier.": (
            "Идентификатор диска Windows некорректен или повторяется."
        ),
        "Reliability counters unavailable for this disk.": (
            "Счётчики надёжности для этого диска недоступны."
        ),
        "The Windows diagnostic response exceeded the size limit.": (
            "Ответ диагностики Windows превысил допустимый размер."
        ),
        "The read-only Windows query failed (exit {code}).": (
            "Ошибка запроса Windows без изменения данных (код {code})."
        ),
        "Windows Storage diagnostics are unavailable on this platform.": (
            "Диагностика Windows Storage недоступна на этой платформе."
        ),
        (
            "Windows storage provider returned {count} disk(s). Counters may be "
            "unavailable or driver defaults."
        ): (
            "Поставщик данных Windows вернул дисков: {count}. Счётчики могут быть "
            "недоступны или содержать значения драйвера по умолчанию."
        ),
        (
            "Windows storage query unavailable. Check provider support and permissions; "
            "no elevation was attempted."
        ): (
            "Запрос хранилища Windows недоступен. Проверьте поддержку поставщика и права "
            "доступа; повышение прав не выполнялось."
        ),
        "A major update requires a separate explicit approval.": (
            "Крупное обновление требует отдельного явного согласия."
        ),
        "A newer stable release is available: {version}.": (
            "Доступна новая стабильная версия: {version}."
        ),
        "A release asset exceeds the permitted download size.": (
            "Файл выпуска превышает допустимый размер загрузки."
        ),
        "A stable version must have the form 1.2.3 or v1.2.3.": (
            "Стабильная версия должна иметь вид 1.2.3 или v1.2.3."
        ),
        "A staged update already exists; it was not overwritten.": (
            "Загруженное обновление уже существует; файл не перезаписан."
        ),
        "Cannot reach GitHub to check for updates.": (
            "Не удалось подключиться к GitHub для проверки обновлений."
        ),
        "Explicit approval is required for this release download.": (
            "Для загрузки этого выпуска необходимо явное согласие."
        ),
        "GitHub release checking failed with HTTP {status}.": (
            "Ошибка проверки выпусков GitHub: HTTP {status}."
        ),
        "GitHub release metadata exceeds the permitted size.": (
            "Метаданные выпуска GitHub превышают допустимый размер."
        ),
        "GitHub returned an invalid SHA256 digest.": (
            "GitHub вернул некорректную контрольную сумму SHA256."
        ),
        "GitHub returned duplicate release asset names.": (
            "GitHub вернул повторяющиеся имена файлов выпуска."
        ),
        "GitHub returned invalid release assets.": "GitHub вернул некорректные файлы выпуска.",
        "GitHub returned invalid release metadata.": (
            "GitHub вернул некорректные метаданные выпуска."
        ),
        "No newer stable release is available.": "Новой стабильной версии нет.",
        "No published GitHub release is available, or access is denied.": (
            "Опубликованный выпуск GitHub недоступен либо доступ запрещён."
        ),
        "No stable published release is available.": "Опубликованной стабильной версии нет.",
        "Only a newer checked release can be staged.": (
            "Загрузить можно только проверенный выпуск более новой версии."
        ),
        "Release download failed with HTTP {status}.": "Ошибка загрузки выпуска: HTTP {status}.",
        "Release integrity verification failed; the download was removed.": (
            "Проверка целостности выпуска не пройдена; загруженный файл удалён."
        ),
        "The release asset does not belong to this repository and tag.": (
            "Файл выпуска не принадлежит этому репозиторию и тегу."
        ),
        "The release contains an unsafe asset filename.": "Выпуск содержит небезопасное имя файла.",
        "The release contains an untrusted download address.": (
            "Выпуск содержит недоверенный адрес загрузки."
        ),
        "The release could not be safely staged; no update was installed.": (
            "Не удалось безопасно подготовить выпуск; обновление не установлено."
        ),
        "The release download exceeds its declared size.": (
            "Загрузка выпуска превышает заявленный размер."
        ),
        "The release download failed; no update was installed.": (
            "Не удалось загрузить выпуск; обновление не установлено."
        ),
        "The release download has an invalid size.": "Размер загруженного выпуска некорректен.",
        "The release download has too many or invalid redirects.": (
            "При загрузке выпуска получены некорректные или слишком многочисленные перенаправления."
        ),
        "The release page does not belong to this repository.": (
            "Страница выпуска не принадлежит этому репозиторию."
        ),
        "The selected asset has no verifiable GitHub SHA256 digest.": (
            "Для выбранного файла нет проверяемой контрольной суммы SHA256 от GitHub."
        ),
        "The update staging directory changed during verification.": (
            "Каталог загрузки обновления изменился во время проверки."
        ),
        "The update staging directory must be an absolute path.": (
            "Путь к каталогу загрузки обновлений должен быть абсолютным."
        ),
        "The update staging path is not a directory.": (
            "Путь загрузки обновлений не является каталогом."
        ),
        "Update download cancelled.": "Загрузка обновления отменена.",
        "Update staging cannot use symbolic links or junctions.": (
            "Для загрузки обновления нельзя использовать символические ссылки или точки соединения."
        ),
        "Explicit speech providers are connected; no automatic recording is enabled.": (
            "Подключены явно выбранные речевые модули; автоматическая запись отключена."
        ),
        "No validated speech provider is connected.": "Проверенный речевой модуль не подключён.",
        "Speech input must be nonempty audio bytes within the size limit.": (
            "Речевой ввод должен содержать непустые аудиоданные допустимого размера."
        ),
        "Speech output must be nonempty text within the size limit.": (
            "Для озвучивания нужен непустой текст допустимого размера."
        ),
        "Speech output must contain valid Unicode text.": (
            "Текст для озвучивания должен содержать корректный Unicode."
        ),
        "Speech playback failed: {error}": "Ошибка воспроизведения речи: {error}",
        "Speech playback is unavailable for this language.": (
            "Воспроизведение речи для этого языка недоступно."
        ),
        "Speech provider check failed: {error}": "Ошибка проверки речевого модуля: {error}",
        "Speech recognition failed: {error}": "Ошибка распознавания речи: {error}",
        "Speech recognition is unavailable for this language.": (
            "Распознавание речи для этого языка недоступно."
        ),
        "The speech operation was cancelled.": "Речевая операция отменена.",
        "The speech provider returned an invalid transcript.": (
            "Речевой модуль вернул некорректный распознанный текст."
        ),
        "The speech provider returned invalid capabilities.": (
            "Речевой модуль вернул некорректные сведения о возможностях."
        ),
        ("Voice assistance is unavailable without validated recognition and speech providers."): (
            "Голосовой помощник недоступен без проверенных модулей распознавания и "
            "воспроизведения речи."
        ),
        "Remote control": "Удалённое управление",
        "Russian": "Русский",
        "English": "Английский",
        "Pairing token": "Токен сопряжения",
        "Connect": "Подключиться",
        "Status": "Состояние",
        "Stop generation": "Остановить генерацию",
        "Apply profile": "Применить профиль",
        "Keep this page on a trusted local network. No hardware writes are available.": (
            "Используйте эту страницу только в доверенной локальной сети. Изменение "
            "настроек оборудования недоступно."
        ),
        "Enter the token shown in NEXUS AI. It is kept only in this page memory.": (
            "Введите токен из NEXUS AI. Он хранится только в памяти этой страницы."
        ),
        "Connection failed. Verify the certificate, address and token.": (
            "Не удалось подключиться. Проверьте сертификат, адрес и токен."
        ),
        "Connected": "Подключено",
    }
)

RU.update(
    {
        "Add game": "Добавить игру",
        "Allow unloading models used by NEXUS for this game": (
            "Разрешить выгрузку моделей NEXUS для этой игры"
        ),
        "Approve download": "Разрешить загрузку",
        "Approve major update": "Разрешить крупное обновление",
        "Cancel download": "Отменить загрузку",
        "Check GitHub Releases": "Проверить выпуски GitHub",
        "Check failed: {error}": "Ошибка проверки: {error}",
        "Checking in the background…": "Проверка в фоновом режиме…",
        "Completed conversations are saved locally on this computer.": (
            "Завершённые ответы сохраняются локально на этом компьютере."
        ),
        "Consumed wear: {value}% (not remaining health)": (
            "Израсходованный ресурс: {value}% (это не остаток ресурса)"
        ),
        "Conversation deleted.": "Беседа удалена.",
        "Conversation restored from local storage.": (
            "Беседа восстановлена из локального хранилища."
        ),
        "Conversation saved locally.": "Беседа сохранена локально.",
        "Delete conversation": "Удалить беседу",
        "Detected names are evidence only; RGB and fan controls remain disabled.": (
            "Обнаруженные имена подтверждают только наличие устройств; управление RGB и "
            "вентиляторами отключено."
        ),
        "Disk: {name} ({kind}, {bus})": "Диск: {name} ({kind}, {bus})",
        "Download and verify": "Загрузить и проверить",
        "Download and verify {asset}? No installation will run.": (
            "Загрузить и проверить {asset}? Установка не будет запущена."
        ),
        "Enable automatic game detection": "Включить автоматическое обнаружение игр",
        "Executable names separated by semicolons, e.g. game.exe; launcher.exe": (
            "Имена исполняемых файлов через точку с запятой, например game.exe; launcher.exe"
        ),
        "Game Guard error: {detail}": "Ошибка защиты игрового режима: {detail}",
        "Game name": "Название игры",
        "Installation unavailable": "Установка недоступна",
        "New conversation": "Новая беседа",
        "New conversation. Completed turns will be saved locally.": (
            "Новая беседа. Завершённые ответы будут сохранены локально."
        ),
        "No candidate detected": "Подходящее устройство не обнаружено",
        "No verifiable SHA256; download disabled": (
            "Нет проверяемой суммы SHA256; загрузка отключена"
        ),
        "Not checked. Run a read-only check when ready.": (
            "Проверка не выполнялась. Запустите диагностику без изменения устройств."
        ),
        (
            "Only configured executable names are detected. No processes are stopped. "
            "Ollama model residency is shared: unloading a NEXUS-used model can affect "
            "other clients using that same model."
        ): (
            "Обнаруживаются только заданные имена исполняемых файлов. Процессы не "
            "останавливаются. Модели Ollama общие для всех клиентов: выгрузка модели "
            "NEXUS может повлиять на другие приложения, использующие ту же модель."
        ),
        "Only stable releases from misha2271/NEXUS-AI are checked.": (
            "Проверяются только стабильные выпуски misha2271/NEXUS-AI."
        ),
        "Permanently delete this locally saved conversation?": (
            "Безвозвратно удалить эту локально сохранённую беседу?"
        ),
        "Power-on hours: {value}": "Время работы, ч: {value}",
        "Provider health: {health}; operations: {operations}": (
            "Состояние по данным поставщика: {health}; работа: {operations}"
        ),
        "Read XInput state": "Получить состояние XInput",
        "Read errors: {read}; write errors: {write}": (
            "Ошибки чтения: {read}; ошибки записи: {write}"
        ),
        ("Read-only XInput snapshot. Elite identity, paddles and rumble are not supported."): (
            "Снимок состояния XInput без управления устройством. Определение модели "
            "Elite, лепестки и вибрация не поддерживаются."
        ),
        "Refresh conversations": "Обновить список бесед",
        "Remove selected game": "Удалить выбранную игру",
        "Restore NEXUS model on demand": "Загрузить модель NEXUS по запросу",
        "Resume conversation": "Продолжить беседу",
        "Run read-only diagnostics": "Запустить диагностику без изменения устройств",
        "SHA256 available": "Сумма SHA256 доступна",
        "SHA256 verifies integrity against GitHub metadata, not publisher identity.": (
            "SHA256 проверяет целостность по метаданным GitHub, но не подлинность издателя."
        ),
        "SHA256: {digest}": "SHA256: {digest}",
        "Slot {slot}: buttons {buttons}": "Слот {slot}: кнопки {buttons}",
        "Some XInput slots could not be read. No controls were written.": (
            "Не удалось прочитать некоторые слоты XInput. Команды управления не отправлялись."
        ),
        "Sticks: left ({lx}, {ly}), right ({rx}, {ry})": (
            "Стики: левый ({lx}, {ly}), правый ({rx}, {ry})"
        ),
        "Temperature: {value} °C": "Температура: {value} °C",
        "The Windows XInput provider is unavailable.": (
            "Поставщик данных XInput в Windows недоступен."
        ),
        "This changes the major version. Explicitly approve this download?": (
            "Обновление меняет основную версию. Явно разрешить эту загрузку?"
        ),
        "Triggers: left {left}, right {right}": "Курки: левый {left}, правый {right}",
        "Untitled conversation": "Без названия",
        "Update download cancellation requested.": "Запрошена отмена загрузки обновления.",
        "Verified download saved to {path}. Nothing was installed.": (
            "Проверенный файл сохранён: {path}. Установка не выполнялась."
        ),
        "Wait for the model operation before changing the server.": (
            "Дождитесь завершения операции с моделью перед сменой сервера."
        ),
        "Windows Storage reliability counters; unavailable fields are not estimates.": (
            "Счётчики надёжности Windows Storage; недоступные значения не заменяются оценками."
        ),
        "XInput diagnostics require native Windows.": "Для диагностики XInput требуется Windows.",
        "XInput returned {count} connected controller(s).": (
            "Подключённых контроллеров по данным XInput: {count}."
        ),
    }
)

RU.update(
    {
        "Approved command completed.": "Разрешённая команда выполнена.",
        "Check GitHub Releases and verify explicitly approved downloads.": (
            "Проверяйте выпуски GitHub и целостность загрузок, на которые вы явно согласились."
        ),
        (
            "Checks use the official repository. Downloads require explicit approval and "
            "a GitHub SHA-256 asset digest; major updates need separate approval. Hash "
            "verification is not publisher signing. Installation remains unavailable."
        ): (
            "Проверяется официальный репозиторий. Для загрузки нужны явное согласие и "
            "сумма SHA-256 файла от GitHub; крупные обновления требуют отдельного "
            "согласия. Контрольная сумма не заменяет подпись издателя. Установка "
            "недоступна."
        ),
        "Current profile: {profile}": "Текущий профиль: {profile}",
        "Local bind address": "Локальный адрес прослушивания",
        "Microphone and speech · unavailable": "Микрофон и речь · недоступно",
        (
            "Opt-in exact executable detection switches inference profiles and restores "
            "the previous profile on game exit. Only NEXUS-used models may be unloaded "
            "with consent. FPS capture, OS tuning, and fan control remain unavailable."
        ): (
            "После явного включения обнаружение точных имён исполняемых файлов "
            "переключает профиль вычислений и восстанавливает предыдущий при выходе из "
            "игры. С согласия пользователя выгружаются только модели, использованные "
            "NEXUS. Измерение FPS, настройка ОС и управление вентиляторами недоступны."
        ),
        "Port (0 selects an available port)": "Порт (0 — выбрать свободный)",
        (
            "Read-only Windows hardware inventory can identify candidates, not SDK "
            "support. No RGB SDK is validated; no HID packets or lighting commands are "
            "sent."
        ): (
            "Сведения об оборудовании Windows позволяют найти возможные устройства, но не"
            " подтверждают поддержку SDK. Проверенного SDK для RGB нет; пакеты HID и "
            "команды подсветки не отправляются."
        ),
        "Read-only diagnostics for standard XInput controller slots.": (
            "Диагностика стандартных слотов контроллеров XInput без изменения устройств."
        ),
        "Remote control is listening at {address}.": (
            "Удалённое управление ожидает подключения по адресу {address}."
        ),
        (
            "Remote control is off by default. LAN access requires your own trusted TLS "
            "certificate. Approved commands: status, stop generation and change profile."
        ): (
            "Удалённое управление по умолчанию отключено. Для доступа по локальной сети "
            "нужен ваш доверенный сертификат TLS. Разрешённые команды: состояние, "
            "остановка генерации и смена профиля."
        ),
        "Remote control is stopped.": "Удалённое управление остановлено.",
        "Run approved text command": "Выполнить разрешённую текстовую команду",
        "Show pairing token": "Показать токен сопряжения",
        "Start remote control": "Запустить удалённое управление",
        "Stop remote control": "Остановить удалённое управление",
        "TLS certificate file": "Файл сертификата TLS",
        "TLS private key file": "Файл закрытого ключа TLS",
        "Text command, e.g. статус or игровой режим": (
            "Текстовая команда, например «статус» или «игровой режим»"
        ),
        "The application is closing.": "Приложение закрывается.",
        "This command is not allowed.": "Эта команда не разрешена.",
        "Update selected game": "Обновить выбранную игру",
        "Voice and remote access": "Голос и удалённый доступ",
        (
            "Windows XInput reports connected slots, buttons, axes, and battery "
            "information when available. Elite-specific paddles, rumble, calibration, and"
            " firmware writes remain unavailable. A slot does not identify an Elite "
            "model."
        ): (
            "Windows XInput сообщает о подключённых слотах, кнопках, осях и батарее, если"
            " данные доступны. Лепестки Elite, вибрация, калибровка и изменение прошивки "
            "недоступны. Номер слота не определяет модель Elite."
        ),
        "Write drive firmware": "Записать прошивку диска",
        "You": "Вы",
        "ON DEMAND · NO HARDWARE WRITES": "ПО ЗАПРОСУ · БЕЗ ИЗМЕНЕНИЯ УСТРОЙСТВ",
    }
)

RU.update(
    {
        (
            "Xbox-family PnP names do not prove Elite Series 2 identity or paddle support. "
            "Standard XInput state can be read separately; Elite features, GameInput and rumble "
            "remain unvalidated and disabled."
        ): (
            "Имена PnP семейства Xbox не подтверждают модель Elite Series 2 или поддержку "
            "лепестков. Стандартное состояние XInput можно прочитать отдельно; функции Elite, "
            "GameInput и вибрация не проверены и отключены."
        ),
    }
)

RU.update(
    {
        (
            "Read-only Windows Storage reliability counters report only fields exposed by the "
            "drive and driver. Missing counters remain unavailable; wear is consumed wear, "
            "not a computed health score. No drive writes are performed."
        ): (
            "Счётчики надёжности Windows Storage доступны только для чтения и показывают "
            "лишь данные, предоставленные диском и драйвером. Отсутствующие счётчики остаются "
            "недоступными; износ означает израсходованный ресурс, а не расчётную оценку "
            "состояния. Запись на диск не выполняется."
        ),
    }
)

RU.update(
    {
        (
            "A clear space to think.\n\nChoose an installed model, then start a conversation.\n"
            "Completed turns are saved locally; prompts go to your configured Ollama server."
        ): (
            "Пространство для ваших идей.\n\nВыберите установленную модель и начните беседу.\n"
            "Завершённые ответы сохраняются локально; запросы отправляются на указанный "
            "вами сервер Ollama."
        ),
        (
            "Windows XInput reports connected slots, buttons, triggers, and stick axes when "
            "available. Elite-specific paddles, rumble, calibration, and firmware writes "
            "remain unavailable. A slot does not identify an Elite model."
        ): (
            "Windows XInput сообщает о подключённых слотах, кнопках, курках и осях стиков, "
            "если данные доступны. Лепестки Elite, вибрация, калибровка и изменение прошивки "
            "недоступны. Номер слота не определяет модель Elite."
        ),
    }
)
