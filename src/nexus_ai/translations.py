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
