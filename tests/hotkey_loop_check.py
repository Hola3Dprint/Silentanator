"""Verify hotkey delivery while Tk is processing its own event queue."""
import ctypes
from ctypes import wintypes as W
import tkinter as tk
from silentanator.windows import Hotkeys, user

root = tk.Tk()
root.withdraw()
keys = Hotkeys(['Ctrl+Alt+F21', 'Ctrl+Alt+Shift+0'])
seen = []
user.PostThreadMessageW.argtypes = [W.DWORD, W.UINT, W.WPARAM, W.LPARAM]
owner = getattr(keys, 'thread_id', ctypes.windll.kernel32.GetCurrentThreadId())

def poll():
    seen.extend(keys.poll())
    root.after(35, poll)

def send():
    assert user.PostThreadMessageW(owner, 0x0312, 1, 0), 'Could not post test hotkey'
    assert user.PostThreadMessageW(owner, 0x0312, 102, 0), 'Could not post numpad alias'

root.after(10, poll)
root.after(50, send)
root.after(250, root.quit)
try:
    root.mainloop()
finally:
    keys.close()
    root.destroy()
assert seen == [1, 2], f'Tk lost the hotkey message or numpad alias: {seen}'
print('Hotkey delivered successfully while Tk mainloop is active.')
