"""Read-only XInput contract and honest unsupported-device reporting."""

from nexus_ai.gamepad import GamepadDiagnostics, _State


def test_other_platform_never_loads_windows_libraries():
    def forbidden():
        raise AssertionError("must not load Windows DLL")

    report = GamepadDiagnostics(platform="linux", reader_factory=forbidden).collect()
    assert not report.available and report.controllers == ()


def test_xinput_reads_only_four_slots_and_preserves_real_values():
    calls = []

    def read(slot):
        calls.append(slot)
        state = _State()
        state.packet = 2
        state.gamepad.buttons = 0x1000
        state.gamepad.left_trigger = 255
        state.gamepad.right_trigger = 17
        state.gamepad.left_x = -32768
        state.gamepad.left_y = 32767
        state.gamepad.right_x = 42
        state.gamepad.right_y = -42
        return (0 if slot == 1 else 1167), state

    report = GamepadDiagnostics(platform="win32", reader_factory=lambda: read).collect()
    assert calls == [0, 1, 2, 3]
    assert report.available and len(report.controllers) == 1
    reading = report.controllers[0]
    assert reading.slot == 1 and reading.buttons == 0x1000
    assert reading.left_x == -32768 and reading.left_y == 32767
    assert reading.left_trigger == 255 and reading.right_trigger == 17
    assert reading.right_x == 42 and reading.right_y == -42
    assert not hasattr(reading, "elite_identity")
    assert not hasattr(reading, "paddles")


def test_no_connected_controllers_is_not_a_fake_device():
    report = GamepadDiagnostics(
        platform="win32", reader_factory=lambda: lambda slot: (1167, _State())
    ).collect()
    assert report.available and report.controllers == ()
    assert "0 connected" in report.message


def test_unexpected_slot_error_is_visible():
    report = GamepadDiagnostics(
        platform="win32", reader_factory=lambda: lambda slot: (5, _State())
    ).collect()
    assert report.available and report.controllers == ()
    assert "could not be read" in report.message


def test_missing_system_dll_is_unavailable():
    def unavailable():
        raise OSError("DLL missing")

    report = GamepadDiagnostics(platform="win32", reader_factory=unavailable).collect()
    assert not report.available and not report.controllers


def test_dll_loading_is_restricted_to_windows_system_directory(monkeypatch):
    import ctypes

    from nexus_ai import gamepad

    loads = []

    class Function:
        def __init__(self, callback):
            self.callback = callback

        def __call__(self, *args):
            return self.callback(*args)

    def directory(buffer, size):
        buffer.value = "C:/Windows/System32"
        return len(buffer.value)

    def state(slot, pointer):
        actual = ctypes.cast(pointer, ctypes.POINTER(gamepad._State)).contents
        actual.gamepad.buttons = 32
        return 0

    class Library:
        GetSystemDirectoryW = Function(directory)
        XInputGetState = Function(state)

    def loader(path, **kwargs):
        loads.append((path, kwargs))
        return Library()

    monkeypatch.setattr(ctypes, "WinDLL", loader, raising=False)
    reader = gamepad._system_state_reader()
    assert reader(0)[1].gamepad.buttons == 32
    assert loads[0] == ("kernel32", {"winmode": 0x800})
    assert loads[1][0].replace("\\", "/") == "C:/Windows/System32/xinput1_4.dll"
    assert loads[1][1] == {"winmode": 0x800}
    assert len(loads) == 2
