"""Read-only XInput state. No rumble, remapping, HID writes or Elite claims."""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from nexus_ai.i18n import Text


class _Gamepad(ctypes.Structure):
    _fields_ = [
        ("buttons", ctypes.c_uint16),
        ("left_trigger", ctypes.c_uint8),
        ("right_trigger", ctypes.c_uint8),
        ("left_x", ctypes.c_int16),
        ("left_y", ctypes.c_int16),
        ("right_x", ctypes.c_int16),
        ("right_y", ctypes.c_int16),
    ]


class _State(ctypes.Structure):
    _fields_ = [("packet", ctypes.c_uint32), ("gamepad", _Gamepad)]


@dataclass(frozen=True)
class GamepadReading:
    slot: int
    buttons: int
    left_trigger: int
    right_trigger: int
    left_x: int
    left_y: int
    right_x: int
    right_y: int


@dataclass(frozen=True)
class GamepadReport:
    available: bool
    controllers: tuple[GamepadReading, ...]
    message: str


def _system_state_reader() -> Callable[[int], tuple[int, _State]]:
    """Only load the Windows system DLL; never search cwd or PATH for XInput."""
    loader = ctypes.WinDLL
    kernel = loader("kernel32", winmode=0x00000800)
    function = kernel.GetSystemDirectoryW
    function.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    function.restype = ctypes.c_uint32
    buffer = ctypes.create_unicode_buffer(32768)
    size = function(buffer, len(buffer))
    if not size or size >= len(buffer):
        raise OSError("Windows system directory unavailable")
    library = None
    for name in ("xinput1_4.dll", "xinput9_1_0.dll"):
        try:
            library = loader(str(Path(buffer.value) / name), winmode=0x00000800)
            break
        except OSError:
            continue
    if library is None:
        raise OSError("Windows XInput unavailable")
    get_state = library.XInputGetState
    get_state.argtypes = [ctypes.c_uint32, ctypes.POINTER(_State)]
    get_state.restype = ctypes.c_uint32

    def read(slot: int) -> tuple[int, _State]:
        state = _State()
        return get_state(slot, ctypes.byref(state)), state

    return read


class GamepadDiagnostics:
    def __init__(
        self,
        *,
        platform: str | None = None,
        reader_factory: Callable = _system_state_reader,
    ):
        self.platform = sys.platform if platform is None else platform
        self.reader_factory = reader_factory

    def collect(self) -> GamepadReport:
        if self.platform != "win32":
            return GamepadReport(False, (), Text("XInput diagnostics require native Windows."))
        try:
            reader = self.reader_factory()
            readings = []
            failed = False
            for slot in range(4):
                code, state = reader(slot)
                if code == 1167:  # ERROR_DEVICE_NOT_CONNECTED; absence is not provider failure.
                    continue
                if code != 0:
                    failed = True
                    continue
                gamepad = state.gamepad
                readings.append(
                    GamepadReading(
                        slot,
                        gamepad.buttons,
                        gamepad.left_trigger,
                        gamepad.right_trigger,
                        gamepad.left_x,
                        gamepad.left_y,
                        gamepad.right_x,
                        gamepad.right_y,
                    )
                )
            message = (
                Text("Some XInput slots could not be read. No controls were written.")
                if failed
                else Text("XInput returned {count} connected controller(s).", count=len(readings))
            )
            return GamepadReport(True, tuple(readings), message)
        except (OSError, AttributeError):
            return GamepadReport(False, (), Text("The Windows XInput provider is unavailable."))
