import time
import unittest
from silentanator.hotkey_recorder import shortcut_from_keypress
from silentanator.setup import validate_shortcuts
from silentanator.core import DEFAULTS
from silentanator.windows import Hotkeys, SingleInstance, hotkey_recording_active, parse_hotkey, user


class RecorderTests(unittest.TestCase):
    def test_record_modifiers_and_physical_key_not_shifted_character(self):
        self.assertEqual(shortcut_from_keypress(ord('0'), 4 | 1), 'Ctrl+Shift+0')
        self.assertEqual(shortcut_from_keypress(ord('K'), 4 | 1 | 8), 'Ctrl+Shift+K')
        self.assertEqual(shortcut_from_keypress(ord('K'), 4 | 0x20000), 'Ctrl+Alt+K')
        self.assertEqual(shortcut_from_keypress(0x70, 4), 'Ctrl+F1')
        self.assertEqual(shortcut_from_keypress(0x60, 4), 'Ctrl+Numpad0')
        self.assertEqual(parse_hotkey(shortcut_from_keypress(0x25, 4))[1], 0x25)
        self.assertIsNone(shortcut_from_keypress(0x11, 4))
        with self.assertRaises(ValueError):
            shortcut_from_keypress(ord('K'), 0)

    def test_recorded_shortcuts_respect_duplicates_and_batches(self):
        with self.assertRaisesRegex(ValueError, 'distinct'):
            validate_shortcuts({**DEFAULTS, 'text': 'Ctrl+Numpad0'})
        with self.assertRaisesRegex(ValueError, 'reserved'):
            validate_shortcuts({**DEFAULTS, 'text': 'Ctrl+Numpad2'})

    def test_global_hotkeys_are_released_and_restored_while_recording(self):
        keys = Hotkeys(['Ctrl+Alt+F20'])
        guard = None
        try:
            guard = SingleInstance('Local\\SilentanatorHotkeyRecording')
            self.assertTrue(hotkey_recording_active())
            deadline = time.monotonic() + 2
            while keys.ids and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(keys.ids)
            self.assertTrue(user.RegisterHotKey(None, 0x4556, *parse_hotkey('Ctrl+Alt+F20')))
            user.UnregisterHotKey(None, 0x4556)
            guard.close()
            guard = None
            deadline = time.monotonic() + 2
            while not keys.ids and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(keys.ids)
            with self.assertRaises(RuntimeError):
                Hotkeys(['Ctrl+Alt+F20'])
        finally:
            if guard:
                guard.close()
            keys.close()
