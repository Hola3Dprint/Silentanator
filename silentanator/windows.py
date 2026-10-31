"""Small Windows API layer; no keyboard recording or injected hooks."""
import ctypes
from ctypes import wintypes as W
import queue
import threading

user = ctypes.WinDLL('user32', use_last_error=True)
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.CreateMutexW.argtypes = [W.LPVOID, W.BOOL, W.LPCWSTR]
kernel.CreateMutexW.restype = W.HANDLE
kernel.CloseHandle.argtypes = [W.HANDLE]
user.RegisterHotKey.argtypes = [W.HWND, ctypes.c_int, W.UINT, W.UINT]
user.UnregisterHotKey.argtypes = [W.HWND, ctypes.c_int]
user.PeekMessageW.argtypes = [ctypes.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT]
user.GetForegroundWindow.restype = W.HWND
user.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]


def parse_hotkey(text):
    parts = [p.strip().upper() for p in text.split('+')]
    modifiers = {'CTRL': 2, 'CONTROL': 2, 'ALT': 1, 'SHIFT': 4, 'WIN': 8}
    mods = 0x4000  # MOD_NOREPEAT
    for part in parts[:-1]:
        if part not in modifiers:
            raise ValueError('Use modifiers Ctrl, Alt, Shift, or Win.')
        mods |= modifiers[part]
    key = parts[-1]
    if len(key) == 1 and key.isascii() and key.isalnum():
        code = ord(key)
    elif (key.startswith('NUMPAD') and key[6:] in tuple(str(i) for i in range(10))):
        code = 0x60 + int(key[6:])
    elif key.startswith('F') and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        code = 111 + int(key[1:])
    else:
        raise ValueError('Use a letter, digit, or F1 through F24 as the hotkey.')
    if mods == 0x4000:
        raise ValueError('Include at least one modifier such as Ctrl.')
    return mods, code


class Hotkeys:
    def __init__(self, keys):
        self.ids = []
        self.messages = queue.Queue()
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self.listen, args=(keys,), daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            self.close()
            raise RuntimeError('The hotkey listener did not start.')
        if self.error:
            raise self.error

    def listen(self, keys):
        # Register and receive on a dedicated thread. Tk consumes thread messages
        # on its GUI thread before a timer-based PeekMessage can inspect them.
        self.thread_id = kernel.GetCurrentThreadId()
        bindings = {}
        try:
            for index, key in enumerate(keys, 1):
                mods, code = parse_hotkey(key)
                if not user.RegisterHotKey(None, index, mods, code):
                    raise RuntimeError(f'Hotkey {key} is already in use. Change it in Setup.')
                self.ids.append(index)
                bindings[index] = index
                # Ctrl+0 accepts either zero key, without changing the chosen shortcut.
                if code == ord('0'):
                    alias = index + 100
                    if user.RegisterHotKey(None, alias, mods, 0x60):
                        self.ids.append(alias)
                        bindings[alias] = index
            self.ready.set()
            message = W.MSG()
            while not self.stop.is_set():
                while user.PeekMessageW(ctypes.byref(message), None, 0x0312, 0x0312, 1):
                    if message.wParam in bindings:
                        self.messages.put(bindings[message.wParam])
                self.stop.wait(0.01)
        except Exception as exc:
            self.error = exc
        finally:
            for index in self.ids:
                user.UnregisterHotKey(None, index)
            self.ids.clear()
            self.ready.set()

    def poll(self):
        while True:
            try:
                yield self.messages.get_nowait()
            except queue.Empty:
                return

    def close(self):
        self.stop.set()
        self.thread.join(timeout=1)


class SingleInstance:
    def __init__(self):
        self.handle = kernel.CreateMutexW(None, False, 'Local\\SilentanatorRunner')
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:
            kernel.CloseHandle(self.handle)
            raise RuntimeError('The background runner is already running.')

    def close(self):
        kernel.CloseHandle(self.handle)


def enable_dpi():
    try:
        user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        user.SetProcessDPIAware()


def capture_bounds(scope):
    if scope == 'active':
        rect = W.RECT()
        if not user.GetWindowRect(user.GetForegroundWindow(), ctypes.byref(rect)):
            raise RuntimeError('Cannot locate the active window.')
        bounds = rect.left, rect.top, rect.right, rect.bottom
        if rect.right <= rect.left or rect.bottom <= rect.top:
            raise RuntimeError('The active window is minimized or has no visible area.')
        return bounds
    return None


def no_activate(window):
    user.GetParent.argtypes = [W.HWND]
    user.GetParent.restype = W.HWND
    hwnd = user.GetParent(window.winfo_id())
    get_style = user.GetWindowLongW
    set_style = user.SetWindowLongW
    get_style.argtypes = [W.HWND, ctypes.c_int]
    set_style.argtypes = [W.HWND, ctypes.c_int, W.LONG]
    set_style(hwnd, -20, get_style(hwnd, -20) | 0x08000000 | 0x80 | 0x20)


def contain_children():
    """Kill subprocesses if Task Manager ends the runner (Windows job object)."""
    class BASIC(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                    ('flags', W.DWORD), ('minimum', ctypes.c_size_t),
                    ('maximum', ctypes.c_size_t), ('active', W.DWORD),
                    ('affinity', ctypes.c_size_t), ('priority', W.DWORD), ('scheduling', W.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ('ro', 'wo', 'oo', 'rt', 'wt', 'ot')]
    class LIMITS(ctypes.Structure):
        _fields_ = [('basic', BASIC), ('io', IO), ('pm', ctypes.c_size_t),
                    ('jm', ctypes.c_size_t), ('pp', ctypes.c_size_t), ('jp', ctypes.c_size_t)]
    kernel.CreateJobObjectW.argtypes = [W.LPVOID, W.LPCWSTR]
    kernel.CreateJobObjectW.restype = W.HANDLE
    kernel.SetInformationJobObject.argtypes = [W.HANDLE, ctypes.c_int, W.LPVOID, W.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [W.HANDLE, W.HANDLE]
    kernel.GetCurrentProcess.restype = W.HANDLE
    handle = kernel.CreateJobObjectW(None, None)
    limits = LIMITS()
    limits.basic.flags = 0x2000
    if not handle or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        kernel.CloseHandle(handle)
        raise ctypes.WinError(ctypes.get_last_error())
    return handle  # Keep open for process lifetime; never inherited by children.
