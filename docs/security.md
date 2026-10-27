# Security checks / Проверки безопасности

## English

Run from an activated project virtual environment:

```console
python -m pip install --upgrade pip "setuptools>=84.1.0"
python -m pip install -e ".[dev,nvidia,security]"
python -m bandit -r src -ll -ii
python -m pip_audit --progress-spinner off
python -m pytest -q
```

CI runs Bandit on application source and fails on medium or high severity findings
with at least medium confidence. It separately audits the actual installed runtime
and security-tool dependencies against PyPI's advisory database. No vulnerability
IDs are ignored. Tooling must also be current: an outdated development `pip` can
cause a dependency audit failure even though it is not bundled in the EXE.
CI also upgrades the runner's preinstalled setuptools before auditing it, rather
than excluding build-tool advisories from the audit.
The local unpublished `nexus-ai-desktop` project cannot be looked up on PyPI;
its source is scanned directly. Advisory checks require network access and do not
establish that every dependency or hardware interface is safe.

The Windows workflow runs the test suite before building both native x64 formats.
It starts each actual frozen executable twice, with an isolated APPDATA and
without build-machine Python or Qt search paths, using the native Windows Qt
plugin. The self-test verifies settings persistence, real CPU/RAM telemetry, the
Russian default, English switching and saved language preferences. ZIP packaging
retains the complete portable runtime. Canonical EXE, ZIP and SHA256SUMS files are
made available only after all requested launches pass. This probe does not
validate attached controllers, storage counters, vendor SDKs or phone connectivity.

GitHub Actions artifacts are test builds, not published releases. Download the
EXE or portable archive and the checksums from the same successful workflow run;
verify the SHA-256 before running. They are retained for 14 days and may require a
GitHub sign-in. SHA-256 detects corruption or a mismatched download; it does not
provide independent code-signing or protect against a compromised GitHub account.

Remote access and model unloading require explicit opt-in. The remote command
allowlist excludes shell execution, file operations, model text and update
installation. Non-loopback remote listeners require user-supplied TLS credentials;
the application does not silently open firewall ports. Conversation data is local
and is not encrypted by the application. Protect the Windows account and its data
directory. Unsupported RGB, fan, audio and firmware write controls stay disabled.

## Русский

Команды выше устанавливают инструменты, проверяют исходный код, известные
уязвимости установленных зависимостей и выполняют тесты. CI останавливается при
находках Bandit средней или высокой серьёзности с достоверностью не ниже средней.
Идентификаторы уязвимостей не исключаются. Проверка pip-audit требует доступа к
базе рекомендаций PyPI. Локальный неопубликованный пакет NEXUS проверяется по
исходному коду, а не по записи в PyPI. Эти проверки не доказывают отсутствие всех
уязвимостей и не заменяют проверку оборудования.

Windows workflow сначала запускает тесты, затем собирает настоящий x64 EXE и
переносимый ZIP. Каждый собранный EXE запускается дважды с отдельным APPDATA,
без путей Python и Qt машины сборки, через штатный плагин Windows. Проверяются
сохранение настроек, реальные показания CPU/RAM, русский язык по умолчанию,
переключение на английский и сохранение языка. Файлы для скачивания и контрольные
суммы появляются только после успешных проверок запуска. Проверка не подтверждает
работу подключённого геймпада, SMART-счётчиков, SDK производителей или iPhone.

Артефакты Actions являются тестовыми сборками, а не опубликованным релизом.
Скачивайте EXE/ZIP и SHA256SUMS из одного успешного запуска и проверяйте SHA-256.
Срок хранения — 14 дней; может потребоваться вход в GitHub. Контрольная сумма
помогает обнаружить повреждение или подмену файла относительно метаданных, но не
заменяет цифровую подпись и не защищает от компрометации учётной записи GitHub.

Удалённое управление и выгрузка моделей требуют явного включения. Разрешённые
удалённые команды не включают оболочку, файловые операции, текст диалогов или
установку обновлений. Для подключения извне loopback нужны предоставленные
пользователем TLS-сертификат и ключ; порты межсетевого экрана автоматически не
открываются. Диалоги хранятся локально без шифрования приложением. Защищайте
учётную запись Windows и каталог данных. Неподдерживаемое управление RGB,
вентиляторами, звуком и прошивками остаётся отключённым.
