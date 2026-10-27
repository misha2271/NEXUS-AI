# Windows installer / Установщик Windows

## Русский

`NEXUS-AI-Setup-1.0.0.exe` — обычный установщик программы, отдельный от
одиночного EXE и переносимого ZIP. Для установки приложения не нужны Python,
Git, GitHub или права администратора. Установщик предлагает русский язык первым;
можно выбрать английский. Приложение также по умолчанию использует русский язык.

По умолчанию программа устанавливается в
`%LOCALAPPDATA%\Programs\NEXUS AI`. Создаётся ярлык в меню «Пуск»; ярлык рабочего
стола можно включить по желанию. Удаление доступно через настройки установленных
приложений Windows или `unins000.exe` в каталоге программы. Настройки, игровые
профили и локальные диалоги в `%APPDATA%\NEXUS AI` сохраняются при удалении.
Установщик не закрывает работающие приложения автоматически: перед обновлением
нужно самостоятельно закрыть NEXUS AI.

Ollama, модели, драйверы и SDK производителей в установщик не включены.
Установщик ничего не скачивает, не запускает NEXUS автоматически после установки,
не добавляет службу или автозагрузку и не открывает порты межсетевого экрана.
Сборка предназначена для Windows x64; ARM64 этим установщиком не поддерживается.

Тестовые сборки не имеют подписи коммерческого сертификата. Windows SmartScreen
может показать предупреждение. Скачивайте артефакт и `SHA256SUMS.txt` из одного
успешного запуска GitHub Actions, проверяйте SHA-256. Не отключайте системную
защиту для установки. Контрольная сумма не заменяет цифровую подпись.

Нативный workflow сначала проверяет исходный код и собирает работающий onedir,
затем запускает Inno Setup. Перед загрузкой установщика он выполняет настоящую
тихую установку во временный каталог, два запуска установленного EXE с проверкой
русского/английского языка и сохранения настроек, тихое удаление и проверку
удаления файлов программы и регистрации деинсталлятора. Проверки исходного кода
на Linux используют явно обозначенные тестовые файлы и не считаются сборкой
настоящего Windows EXE.

Для разработчика на чистой учётной записи Windows x64:

```powershell
python -m pip install -e ".[dev,nvidia,freeze]"
python scripts/build_windows.py --mode both
python scripts/build_installer.py --iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

Сначала отдельно установите Inno Setup из официального источника. Скрипт сборки
сам инструменты не скачивает. В GitHub Actions используется предустановленный
компилятор; если его нет, устанавливается пакет `innosetup` из официального
community-репозитория Chocolatey с обязательной проверкой контрольной суммы.
Компиляция не создаёт релиз и ничего не публикует автоматически.

Скрипт отказывается проводить тестовую установку, если для текущего пользователя
уже зарегистрирован NEXUS AI: это защищает существующую установку разработчика.
Собирайте установщик в чистом аккаунте или отдельной машине CI. Путь можно
передать через `--iscc`; нужен современный Inno Setup 6.3 или новее.

## English

`NEXUS-AI-Setup-1.0.0.exe` is the per-user installer, separate from the standalone
EXE and portable ZIP. Installation needs no Python, Git, GitHub account or
administrator privileges. Russian is offered first; English is available.
The application itself also defaults to Russian.

The default destination is `%LOCALAPPDATA%\Programs\NEXUS AI`. Setup creates a
Start menu shortcut and offers an optional desktop shortcut. Remove it through
Windows installed-app settings or the installed `unins000.exe`. Uninstall keeps
preferences, game profiles and local conversations in `%APPDATA%\NEXUS AI`.
Setup does not automatically close running applications; close NEXUS before
updating its installed program files.

The installer bundles no Ollama server, models, drivers or vendor SDKs. It makes
no downloads, does not launch NEXUS after installation, and adds no service,
startup entry or firewall rule. This installer targets x64 Windows and excludes
ARM64. Builds are not commercially code-signed; Windows SmartScreen may warn.
Obtain the installer and SHA256SUMS from the same successful Actions run, verify
the checksum and keep OS security protections enabled. SHA-256 is not code signing.

The native workflow validates the onedir, compiles with Inno Setup, silently
installs the actual installer into a scratch directory, launches the installed
EXE twice with isolated APPDATA to verify RU/EN and settings persistence, then
silently uninstalls it and checks removal of program files and uninstall
registration. Only a successful installer is copied to the canonical download
name and added to SHA256SUMS. Linux orchestration tests use labelled fixtures;
they do not validate an actual Windows installer.

Use the PowerShell commands above on a clean native Windows x64 build account
after separately installing Inno Setup 6.3 or later. `build_installer.py` never
downloads a compiler and refuses to smoke-install over an existing per-user
NEXUS installation. CI prefers the runner's installed compiler, falling back to
the official Chocolatey community source with mandatory checksum verification.
The workflow uploads test artifacts only; it never publishes a release.
