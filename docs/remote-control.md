# Remote control / Удалённое управление

## Русский

Удалённое управление выключено при каждом запуске. Панель позволяет явно
запустить локальный сервер и остановить его, не блокируя интерфейс. Сервер
принимает только три команды: получение состояния, остановку генерации и выбор
одного из четырёх профилей производительности. Произвольные команды, чат,
чтение файлов, установка обновлений, RGB и управление вентиляторами недоступны.

Для проверки на этом же компьютере разрешён HTTP на `127.0.0.1` или `::1`.
Для iPhone в локальной сети нужно указать конкретный локальный IP-адрес
компьютера, доверенный телефоном TLS-сертификат и соответствующий закрытый ключ.
Сертификат должен соответствовать используемому адресу; приложение не создаёт
исключения из проверки сертификатов и не открывает порт в брандмауэре.
Запрещены широковещательные привязки `0.0.0.0`/`::` и multicast. Не публикуйте
сервер в Интернете. Подключение реального iPhone здесь физически не проверено.

После запуска панель показывает адрес и скрытый токен сопряжения. Откройте адрес
на телефоне и вручную введите токен на странице. Токен состоит из 32 случайных
байтов, существует только в памяти текущего сеанса и меняется при новом запуске
сервера. В URL, конфигурационные файлы, журналы и хранилища браузера токен не
записывается. Не передавайте его другим пользователям. Кнопка показа токена
раскрывает его на экране компьютера.

API проверяет Bearer-токен постоянным по времени сравнением, точные Host/Origin,
список команд и структуру JSON. Изменяющие состояние запросы требуют уникальный
nonce; повторение в течение пяти минут отклоняется. Ограничены размер запроса,
размер ответа, время запроса, число соединений, очередь и частота запросов.
Страница имеет ограничительную Content Security Policy, не загружает внешние
ресурсы и по умолчанию использует русский язык; английский доступен в селекторе.

HTTP-потоки не меняют виджеты. Таймер Qt обрабатывает только разрешённые команды
в основном потоке; длительные операции должны оставаться в рабочих потоках
соответствующих модулей. Запрос, истёкший до начала обработки, не выполняется
позже. Если обработчик уже начал команду до истечения тайм-аута, отменить её
задним числом нельзя; перед повтором проверьте состояние. При закрытии окна
приём команд прекращается, а сетевой сервер останавливается в рабочем потоке.

## English

Remote control starts disabled on every application launch. The panel explicitly
starts and stops a listener without blocking the desktop. Its entire command
surface is status, stop generation, and selecting one of four performance modes.
It exposes no arbitrary commands, chat, files, installation, RGB, or fan writes.

HTTP on `127.0.0.1` or `::1` is a local development option. An actual iPhone LAN
connection requires a specific computer IP address, a TLS certificate trusted by
the phone for that address, and its private key. The app neither bypasses TLS
verification nor changes firewall rules. Wildcard and multicast bindings are
rejected. Do not expose this service to the Internet. Physical iPhone operation
has not been tested in the development environment.

The panel displays the address and a masked pairing token. Enter that token on
the page manually. It contains 256 bits of randomness, stays in memory only, and
changes when the listener restarts. Neither the desktop nor the page stores it in
configuration, logs, URLs, localStorage, or sessionStorage. Treat it as a secret;
the reveal button makes it visible to people near the desktop.

Bearer authentication uses constant-time comparison. Exact Host/Origin checks,
an allowlist, strict JSON schema, replay nonces, request/response size limits,
connection limits, rate limits, and deadlines constrain requests. The page has a
restrictive CSP, uses no external resources, and defaults to Russian with English
available. Qt drains approved commands on its main thread while network work
stays in workers. Pending timed-out commands cannot execute later; a command
already executing cannot be rolled back. Check status before retrying. Shutdown
closes the command queue and stops the listener in a worker.

## Verification

`tests/test_remote.py` uses a real loopback listener to exercise authentication,
Host/Origin denial, command rejection, JSON ambiguity rejection, replay handling,
request bounds, rate limits, queue timeout behavior, and CSP script hashes.
`tests/test_remote_panel.py` checks the Qt queue boundary, explicit opt-in,
shutdown during startup, and rejection of LAN HTTP without TLS. These tests do
not establish a physical phone connection or validate a user's certificate.
