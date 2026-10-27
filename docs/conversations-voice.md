# Conversations and Russian voice foundation / Разговоры и голосовой модуль

## English: working conversation persistence

`ConversationStore` uses Python's standard-library SQLite driver. The default file
is `conversations.sqlite3` beside the user's existing NEXUS AI settings. The UI
passes an explicit path when using an isolated settings store and runs operations
in background service jobs. Every operation owns a short-lived connection; SQLite
transactions serialize writers. There is no global connection shared across Qt
threads.

The API is `create(title)`, `list_conversations(limit)`, `load(id)`,
`save(id, messages, title=None, expected_revision=None)` and `delete(id)`.
Create/load/save return `Conversation` with an ID, title, exact message contents,
creation/update timestamps and revision. Lists return summaries with message counts.
Only `user` and `assistant` roles and the `role`/`content` fields are accepted.
No message text is translated, stripped, interpreted as SQL, or executed.

The UI saves completed turns and uses the returned revision in the next
`expected_revision`. A stale write raises `ConversationConflict`; it does not
silently overwrite a later save. Drafts and interrupted partial replies are not
automatically promoted into conversation context by the store. Creating a new chat
never deletes older chats; deletion requires selecting the specific conversation.

The assistant's conversation bar lists stored chats and provides explicit new,
resume, refresh and confirmed delete actions. Startup lists chats without silently
replacing the current context with an old conversation. Background operations are
serialized: multiple completed saves retain turn order, and a pending old-chat save
cannot replace a newly started chat. Closing the window lets queued completed-turn
saves finish without blocking Qt. The unsent draft is not a completed conversation.

Default bounds are 100 conversations, 400 messages per chat, 65,536 characters per
message, one million characters per chat and a 64 MiB database. Constructors accept
stricter limits for deployment/tests. Reaching a limit reports an error without
silently truncating history or deleting an older chat. A failed transaction rolls
back. SQLite schema/version checks reject unsupported databases, invalid records,
and unexpected triggers/views. Corrupt files are preserved; they are not renamed,
recreated, or silently replaced with an empty conversation list.

### Privacy and storage limits

Conversation data is **local plaintext**, not encrypted storage. On POSIX, newly
created directories/files use 0700/0600. Existing permissions are not silently
rewritten. On Windows, inherited per-user ACLs apply; POSIX mode bits do not prove
Windows access protection. Use a protected account/configuration directory.
No authentication-token or audio-recording fields exist in this database, but a
secret explicitly pasted into a prompt is still part of that prompt. Journals,
backups and freed SQLite pages can contain conversation text; deleting a chat is
not a secure physical erase. There is no cloud sync, automatic export or telemetry
upload in this module.

## English: implemented voice contracts, not working audio

`VoiceFoundation` defines separate `SpeechRecognizer` and `SpeechSynthesizer`
protocols. They accept an explicit language and cancellation event and must be
called from a worker thread. No microphone, wake-word listener, speech model,
recognition service, playback engine or voice download is initialized by default.
Both microphone and playback controls must remain disabled without a real,
explicitly configured, available and physically validated language provider.

The provided **text** intent router is working code. It matches complete approved
Russian/English phrases for `status`, `stop_generation`, and switching one of the
four existing canonical profiles. For example, `Нексус, останови ответ!`,
`включи игровой режим`, `экономичный режим`, `show status`, and `switch to eco`.
Compound, unknown, oversized and control-character commands do not execute.
The router returns typed intent data; it does not run a command, open a URL,
execute a shell, install updates, or write RGB/fan/firmware settings.
Recognizing a string in a test is **not** proof of microphone or speech support.

Providers are default-deny: availability without validation, an unsupported
language, invalid capability types, backend failures, pre/post-operation
cancellation and malformed transcripts remain errors. There is no automatic
fallback from Russian to another voice language. The test suite injects explicit
provider doubles to verify these contracts; those doubles are not shipped as
usable audio engines or physical-device validation.

A future Windows provider can investigate documented speech interfaces such as
[System.Speech installed-voice enumeration](https://learn.microsoft.com/en-us/dotnet/api/system.speech.synthesis.speechsynthesizer.getinstalledvoices).
That documentation does not establish that a Russian voice/recognizer is installed
on the user's machine or that packaging and playback have been physically tested.
No SAPI/System.Speech backend is implemented in this version.

## Русский: рабочее сохранение разговоров

`ConversationStore` сохраняет разговоры через стандартный модуль SQLite Python.
Файл `conversations.sqlite3` располагается рядом с настройками NEXUS AI.
Операции выполняются в фоновых заданиях; каждое открывает собственное короткое
соединение. Транзакции сериализуют запись. Пользовательский текст сохраняется
без перевода, обрезки, исполнения SQL или изменения содержимого.

Реализованы создание, список, загрузка, сохранение и удаление конкретного чата.
Сохраняются идентификатор, название, сообщения, время и номер версии записи.
Интерфейс сохраняет завершённые ответы и передаёт `expected_revision` для защиты
от устаревшей асинхронной записи. Конфликт возвращает ошибку, а не затирает более
новый разговор. Черновики и отменённые фрагменты не становятся контекстом сами
по себе; новый чат не удаляет старые.

В строке разговоров помощника доступны список, новый чат, явное продолжение,
обновление списка и удаление с подтверждением. При запуске старый разговор не
подменяет текущий контекст автоматически. Последовательная фоновая очередь
сохраняет порядок завершённых ответов; отложенная запись старого чата не меняет
новый чат. Закрытие окна дожидается записи уже завершённых ответов, сохраняя
отзывчивость интерфейса. Неотправленный черновик не считается сохранённым диалогом.

По умолчанию доступны до 100 чатов, 400 сообщений на чат, 65 536 символов на
сообщение, миллион символов на чат и база до 64 МиБ. Превышение лимита не приводит
к скрытому удалению истории. Ошибочная транзакция откатывается. Повреждённые файлы,
неизвестные схемы и некорректные записи сохраняются для диагностики и не заменяются
пустой базой. Никаких автоматических миграций чужих SQLite-файлов нет.

Данные хранятся локально **без шифрования**. Новые файлы POSIX создаются с правами
0600, каталоги — 0700. В Windows используются унаследованные права учётной записи;
биты режима POSIX не подтверждают защиту ACL. База не содержит специальных полей
токенов или аудиозаписей, однако секрет, вручную вставленный в запрос, останется
частью запроса. Журналы, резервные копии и свободные страницы SQLite могут сохранять
текст; удаление чата не является гарантированным физическим стиранием.

## Русский: голосовая архитектура без имитации аудио

`VoiceFoundation` содержит отдельные контракты распознавания и воспроизведения
речи с явным языком и событием отмены. По умолчанию не запускаются микрофон,
прослушивание ключевого слова, распознавание, воспроизведение или загрузка моделей.
Аудиокнопки должны оставаться выключенными до появления реального поддерживаемого
модуля и проверки на физическом устройстве с нужным языком.

Реализован ограниченный анализ **текстовых** команд: статус, остановка ответа и
переключение четырёх существующих профилей. Примеры: `Нексус, останови ответ!`,
`включи игровой режим`, `экономичный режим`. Неизвестные, составные, слишком
длинные команды и управляющие символы не исполняются. Результат — объект намерения,
а не произвольная команда оболочки. Доступа к установке обновлений, RGB,
вентиляторам, прошивкам, файлам или произвольным URL у анализатора нет.

Наличие признака доступности без подтверждённой проверки не разрешает аудио.
Неподдерживаемый язык не подменяется другим. Ошибки модуля, неправильные типы
возможностей, некорректный результат и отмена возвращают ошибку без выдуманного
текста распознавания. Тестовые реализации нужны только для проверки контрактов
и не являются встроенными рабочими речевыми движками. Наличие настоящего русского
голоса, распознавания и звукового устройства в Windows не проверено; готового
модуля SAPI/System.Speech в этой версии нет.
