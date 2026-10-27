# Update checking and integrity / Проверка обновлений и целостности

The Update Center checks only stable GitHub Releases in `misha2271/NEXUS-AI`, over verified HTTPS. A check is read-only and runs off the UI thread. No release is published by the application. A 404 is reported as no published release **or denied access**, rather than proof that no release exists.

Центр обновлений проверяет только стабильные релизы `misha2271/NEXUS-AI` по HTTPS с проверкой сертификата. Запрос выполняется в фоне. Приложение не публикует релизы. Ответ 404 означает отсутствие доступного опубликованного релиза либо отказ в доступе.

An EXE/ZIP download is available only for a newer checked release and an asset with a valid GitHub `sha256:` digest. The user must confirm that specific asset; a major version change requires a second explicit confirmation. Metadata, filenames, repository/tag URLs, redirect hosts, size and SHA256 are validated. Downloads are written to a bounded staging directory atomically without overwriting existing files; failed verification removes partial content. Cancellation is cooperative between network chunks and remains bounded by HTTP timeouts.

Скачивание EXE/ZIP разрешено только для более нового проверенного релиза с корректным SHA256 из метаданных GitHub. Пользователь подтверждает конкретный файл, а смену основной версии — отдельным подтверждением. Проверяются адреса, репозиторий/тег, имя, перенаправления, размер и контрольная сумма. Файлы сохраняются без перезаписи существующих; при ошибке проверки временный файл удаляется. Отмена выполняется между порциями данных и ограничена тайм-аутами сети.

**Nothing is installed, extracted or executed.** Installation remains visibly disabled. SHA256 establishes consistency with GitHub metadata; it is not independent publisher authentication or an Authenticode signature. A compromised repository/account is outside that integrity guarantee. The runtime API intentionally refuses an asset without a digest rather than inventing a checksum or trusting an unchecked sidecar.

**Ничего не устанавливается, не распаковывается и не запускается.** Кнопка установки отключена. SHA256 подтверждает соответствие метаданным GitHub, но не заменяет подпись издателя/Authenticode и не защищает от компрометации самого репозитория. Файл без проверяемой контрольной суммы не скачивается через этот интерфейс.

Automated tests use controlled HTTP fixtures for valid downloads, malicious URLs, missing/mismatched digests, bounds, cancellation and approval requirements. Actual release asset installation and publisher signature verification are not implemented or claimed. No test release should be published to exercise this feature.

Автотесты используют контролируемые HTTP-ответы для проверки целостности, ограничений, отмены, адресов и разрешений. Установка реального релиза и проверка подписи издателя не реализованы и не заявляются.

References: [GitHub Releases API](https://docs.github.com/en/rest/releases/releases), [GitHub release assets API](https://docs.github.com/en/rest/releases/assets).
