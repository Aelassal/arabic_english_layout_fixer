"""Global hotkey listener that works whatever keyboard layout is active.

pynput's GlobalHotKeys compares typed *characters*, so a hotkey like Ctrl+Alt+A would not fire
while the Arabic layout is on (the A key then types ش). This matches the physical key instead.
"""
import sys

from . import config, core, log

_MOD_NAMES = {
    "ctrl": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "alt": "alt", "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
    "shift": "shift", "shift_l": "shift", "shift_r": "shift",
    "cmd": "cmd", "cmd_l": "cmd", "cmd_r": "cmd",
}
# macOS virtual key codes (ANSI positions, independent of the layout)
_MAC_VK = {0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z", 7: "x", 8: "c", 9: "v", 11: "b",
           12: "q", 13: "w", 14: "e", 15: "r", 16: "y", 17: "t", 18: "1", 19: "2", 20: "3", 21: "4",
           22: "6", 23: "5", 25: "9", 26: "7", 28: "8", 29: "0", 31: "o", 32: "u", 34: "i", 35: "p",
           37: "l", 38: "j", 40: "k", 45: "n", 46: "m", 49: "space"}


def modifier_of(key):
    return _MOD_NAMES.get(getattr(key, "name", None))


def base_key(key):
    """Name of the physical key ('a', '7', 'f5', 'space') or None for keys we don't use."""
    name = getattr(key, "name", None)
    if name:
        return name if name == "space" or (name[0] == "f" and name[1:].isdigit()) else None
    vk = getattr(key, "vk", None)
    if sys.platform.startswith("win") and vk is not None:
        if 0x41 <= vk <= 0x5A:
            return chr(vk).lower()
        if 0x30 <= vk <= 0x39:
            return chr(vk)
    if sys.platform == "darwin" and vk in _MAC_VK:
        return _MAC_VK[vk]
    char = getattr(key, "char", None)
    if not char:
        return None
    if len(char) == 1 and 1 <= ord(char) <= 26:          # Ctrl+letter arrives as a control char
        return chr(96 + ord(char))
    if core.is_arabic(char):                              # Arabic layout active: map back to the key
        char = core.arabic_to_english(char)
    char = char.lower()
    return char if len(char) == 1 and char in config.KEYS else None


class Matcher:
    """Tracks held modifiers and says when the configured hotkey is pressed."""

    def __init__(self, hotkey: str):
        mods, self.key = config.parse(hotkey)
        self.mods = set(mods)
        self.held = set()
        self._fired = False

    def press(self, key) -> bool:
        mod = modifier_of(key)
        if mod:
            self.held.add(mod)
            return False
        if base_key(key) == self.key and self.held == self.mods and not self._fired:
            self._fired = True                            # ignore auto-repeat while held
            return True
        return False

    def release(self, key) -> None:
        mod = modifier_of(key)
        if mod:
            self.held.discard(mod)
        elif base_key(key) == self.key:
            self._fired = False


class HotkeyListener:
    def __init__(self, hotkey: str, callback):
        self.matcher = Matcher(hotkey)
        self.callback = callback
        self._listener = None

    def start(self):
        from pynput import keyboard

        def on_press(key):
            try:
                if self.matcher.press(key):
                    self.callback()
            except Exception:                              # an exception would stop the listener
                log.get().exception("hotkey handler failed")

        def on_release(key):
            try:
                self.matcher.release(key)
            except Exception:
                log.get().exception("hotkey release handler failed")

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None
