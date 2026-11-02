"""Capture a shortcut only while the user has the Record dialog open."""
import tkinter as tk
from tkinter import ttk

from .windows import KEY_NAMES, SingleInstance, parse_hotkey, user


def shortcut_from_keypress(keycode, state, windows=False):
    if keycode in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
        return None
    if ord('0') <= keycode <= ord('9') or ord('A') <= keycode <= ord('Z'):
        key = chr(keycode)
    elif 0x70 <= keycode <= 0x87:
        key = 'F' + str(keycode - 0x6F)
    elif 0x60 <= keycode <= 0x69:
        key = 'Numpad' + str(keycode - 0x60)
    else:
        key = next((name.title() for name, code in KEY_NAMES.items() if code == keycode), None)
        if key is None:
            raise ValueError('Use a letter, digit, function key, or navigation key.')
    modifiers = []
    if state & 4:
        modifiers.append('Ctrl')
    # Windows Tk uses bit 0x20000 for Alt. Bit 8 can be Num Lock and
    # must not add an Alt modifier to every recorded shortcut.
    if state & 0x20000:
        modifiers.append('Alt')
    if state & 1:
        modifiers.append('Shift')
    if windows:
        modifiers.append('Win')
    shortcut = '+'.join([*modifiers, key])
    parse_hotkey(shortcut)
    return shortcut


class HotkeyRecorder:
    def __init__(self, parent, title, on_record):
        # The runner releases its global shortcuts while this handle is alive.
        # Closing the dialog or its process releases the handle automatically.
        try:
            self.guard = SingleInstance('Local\\SilentanatorHotkeyRecording')
        except RuntimeError as exc:
            raise RuntimeError('Another hotkey recorder is already open.') from exc
        self.on_record = on_record
        self.closed = False
        self.window = tk.Toplevel(parent)
        self.window.title('Record ' + title.lower())
        self.window.transient(parent)
        self.window.resizable(False, False)
        frame = ttk.Frame(self.window, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Press your new shortcut', font=('Segoe UI', 14, 'bold')).pack(anchor='w')
        self.message = tk.StringVar(value='Hold Ctrl, Alt, Shift, or Win and press a key.\nEscape cancels without changing the current shortcut.')
        ttk.Label(frame, textvariable=self.message, wraplength=410).pack(anchor='w', pady=12)
        ttk.Button(frame, text='Cancel', command=self.close).pack(anchor='e')
        self.window.bind('<KeyPress>', self.keypress)
        self.window.bind('<Escape>', lambda event: self.close())
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.grab_set()
        self.focus_timer = self.window.after(100, self.window.focus_force)

    def keypress(self, event):
        if event.keycode == 0x1B:
            self.close()
            return 'break'
        try:
            windows = bool(user.GetKeyState(0x5B) & 0x8000 or user.GetKeyState(0x5C) & 0x8000)
            shortcut = shortcut_from_keypress(event.keycode, event.state, windows)
            if shortcut:
                self.on_record(shortcut)
                self.close()
        except ValueError as exc:
            self.message.set(str(exc) + '\nPress another shortcut, or Escape to cancel.')
        return 'break'

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.window.after_cancel(self.focus_timer)
        self.window.grab_release()
        self.window.destroy()
        self.guard.close()
