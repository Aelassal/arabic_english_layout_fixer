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
    """Tracks the *physically* held keys and says when the configured hotkey was used.

    With `fire_on_release` the chord is only armed when it is pressed, and fires once every key of it is
    up again. The tool then starts sending its own keys (Ctrl/Cmd+C, Shift+Insert, ...) after you let go,
    so none of the hotkey's keys can be merged into them (an app that sees Ctrl+Alt+C ignores it).
    Events the tool injected itself (`injected`) are ignored, so they never change the tracked state."""

    def __init__(self, hotkey: str, fire_on_release: bool = False):
        mods, self.key = config.parse(hotkey)
        self.mods = set(mods)
        self.held = set()
        self.fire_on_release = fire_on_release
        self._fired = False
        self._armed = False
        self._main_down = False

    def press(self, key, injected: bool = False) -> bool:
        if injected:
            return False
        mod = modifier_of(key)
        if mod:
            self.held.add(mod)
            return False
        if base_key(key) != self.key:
            self._armed = False                           # another key was typed: not a hotkey press
            return False
        self._main_down = True
        if self.held == self.mods and not self._fired:
            self._fired = True                            # ignore auto-repeat while held
            if self.fire_on_release:
                self._armed = True
                return False
            return True
        return False

    def release(self, key, injected: bool = False) -> bool:
        """True when the hotkey was pressed and every key of it is now up (only with fire_on_release)."""
        if injected:
            return False
        mod = modifier_of(key)
        if mod:
            self.held.discard(mod)
        elif base_key(key) == self.key:
            self._fired = False
            self._main_down = False
        if self._armed and not self.held and not self._main_down:
            self._armed = False
            return True
        return False

    def resync(self, really_held) -> None:
        """Forget modifiers the OS says are up (a release event can get lost, e.g. across a locked screen).
        `really_held` is a list of names from system._held_modifiers(), or None when unknown. A reading
        that lacks one of the hotkey's own modifiers is not trusted, so a wrong reading can never stop
        the hotkey from working."""
        if really_held is None:
            return
        real = {"cmd" if name == "win" else name for name in really_held}
        if self.mods <= real:
            self.held &= real


class HotkeyListener:
    def __init__(self, hotkey: str, callback, state_probe=None):
        self.matcher = Matcher(hotkey, fire_on_release=True)
        self.callback = callback
        self.state_probe = state_probe                     # () -> modifier names physically held, or None
        self._listener = None

    def start(self):
        from pynput import keyboard

        def on_press(key, injected=False):
            try:
                if self.state_probe and not injected and modifier_of(key) is None:
                    self.matcher.resync(self.state_probe())
                self.matcher.press(key, injected)
            except Exception:                              # an exception would stop the listener
                log.get().exception("hotkey handler failed")

        def on_release(key, injected=False):
            try:
                if self.matcher.release(key, injected):
                    log.get().info("hotkey released: starting the fix")
                    self.callback()
            except Exception:
                log.get().exception("hotkey release handler failed")

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None
