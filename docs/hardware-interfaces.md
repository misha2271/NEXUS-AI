# Read-only hardware diagnostics / Диагностика оборудования без записи

## Implemented / Реализовано

- **Windows Storage**: `Get-PhysicalDisk` and `Get-StorageReliabilityCounter`, through the OS PowerShell executable, return provider health, available temperature, consumed wear, power-on hours and error counters. The query runs on a worker and never elevates privileges, writes disks or invents a health percentage. Missing/zero temperature stays unavailable. Consumed wear is **not** remaining health; a provider may expose missing, stale or default values. This is a supported CIM interface, not universal raw vendor SMART parsing.
- **XInput**: a worker reads the four documented controller slots through the absolute System32 `xinput1_4.dll`, with the OS `xinput9_1_0.dll` fallback. The Gamepad page displays buttons, triggers and stick coordinates from a user-requested snapshot. No vibration or other device writes exist. A standard XInput connection does not establish Elite Series 2 identity, paddle access or remapping support. Disconnected controllers do not become synthetic devices.
- **Inventory**: read-only `Win32_BaseBoard`, `Win32_PnPEntity` and optional `Win32_Fan` provide candidate evidence. A matching product name does not validate SDK compatibility, temperature, RPM or controls. Windows provider failures remain visible; Linux reports unsupported honestly.

Реализованы запросы Windows Storage для доступных счётчиков надёжности, чтение четырёх слотов XInput и инвентаризация устройств через CIM. Запросы выполняются в фоновых рабочих задачах. Нет повышения прав, записи на диски, вибрации, управления подсветкой или вентиляторами. Износ — использованный ресурс, а не оставшийся процент здоровья. Нулевые/недоступные температуры не подменяются вымышленными значениями. Обычный XInput не подтверждает модель Elite Series 2 и не предоставляет отдельные лепестки.

## Investigated interfaces / Исследованные интерфейсы

| Interface | Finding / Вывод |
| --- | --- |
| MSI Mystic Light SDK | Vendor SDK documents device enumeration and lighting functions, but licensing, supported board/model, SDK binary provenance and physical behavior must be validated before any write. Совпадение имени MSI не включает управление RGB. |
| Logitech LED SDK / G560 | SDK documentation does not prove G560 support on this machine, nor audio routing or firmware functionality. G560 name detection leaves RGB/audio controls disabled. Требуется реальная проверка совместимого SDK и устройства. |
| Xbox Elite Series 2 | XInput provides standard gamepad state; separate paddles, Elite identity, remapping and rumble remain unsupported here. GameInput may be investigated independently; no invented HID integration. |
| Cooling | `Win32_Fan` inventory does not establish actual RPM or writable cooling control. No generic safe fan-write interface is assumed. Температуры доступны только из реально поддерживаемых поставщиков данных. |

All hardware interfaces are **physically untested in this Linux cloud workspace**. Automated fixtures validate parsing, fixed query boundaries, worker execution and honest missing-provider behavior; they do not validate a physical device or its safety.

Все аппаратные интерфейсы **не проверены на физических устройствах в этой облачной Linux-среде**. Автотесты проверяют обработку ответов, границы запросов, фоновые задачи и отсутствие вымышленных показаний, но не подтверждают поддержку конкретного устройства.

## Primary references / Первичные источники

- Microsoft: [Get-StorageReliabilityCounter](https://learn.microsoft.com/en-us/powershell/module/storage/get-storagereliabilitycounter), [Get-PhysicalDisk](https://learn.microsoft.com/en-us/powershell/module/storage/get-physicaldisk).
- Microsoft: [XInputGetState](https://learn.microsoft.com/en-us/windows/win32/api/xinput/nf-xinput-xinputgetstate), [XInput versions](https://learn.microsoft.com/en-us/windows/win32/xinput/xinput-versions), [XINPUT_GAMEPAD](https://learn.microsoft.com/en-us/windows/win32/api/xinput/ns-xinput-xinput_gamepad).
- Microsoft: [Win32_Fan](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-fan), [GameInput](https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/input/overviews/input-overview).
- MSI: [Mystic Light SDK](https://www.msi.com/Landing/mystic-light-rgb-gaming-pc/download).
- Logitech: [Developer Lab SDKs](https://www.logitechg.com/en-us/innovation/developer-lab.html).
