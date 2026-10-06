"""Small settings window: choose the hotkey. Runs as its own process (--settings)."""
import sys
import tkinter as tk
from tkinter import ttk

from . import config, system


def main():
    root = tk.Tk()
    root.title("Arabic Layout Fixer - Settings")
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=20)
    frm.grid()

    ttk.Label(frm, text="Hotkey that fixes the selected text", font=("", 12, "bold")).grid(
        row=0, column=0, columnspan=4, sticky="w")
    ttk.Label(frm, text="Tick the modifier keys, then pick a key.").grid(
        row=1, column=0, columnspan=4, sticky="w", pady=(0, 12))

    mods, key = config.parse(config.load_hotkey())
    labels = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift",
              "cmd": "Cmd" if config.sys.platform == "darwin" else "Win"}
    available = [m for m in config.MODIFIERS if not (m == "alt" and sys.platform == "darwin")]
    mod_vars = {m: tk.BooleanVar(value=m in mods) for m in available}
    for i, m in enumerate(available):
        ttk.Checkbutton(frm, text=labels[m], variable=mod_vars[m], command=lambda: refresh()).grid(
            row=2, column=i, sticky="w", padx=(0, 12))

    key_var = tk.StringVar(value=key)
    ttk.Label(frm, text="Key:").grid(row=3, column=0, sticky="w", pady=12)
    box = ttk.Combobox(frm, textvariable=key_var, values=config.KEYS, width=8, state="readonly")
    box.grid(row=3, column=1, sticky="w")
    box.bind("<<ComboboxSelected>>", lambda e: refresh())

    preview = ttk.Label(frm, font=("", 11))
    preview.grid(row=4, column=0, columnspan=4, sticky="w")
    status = ttk.Label(frm, foreground="#b00020")
    status.grid(row=5, column=0, columnspan=4, sticky="w")

    def current():
        return config.build([m for m, v in mod_vars.items() if v.get()], key_var.get())

    def refresh():
        try:
            preview.config(text="Hotkey:  " + config.pretty(current()))
            status.config(text="")
            return True
        except ValueError:
            preview.config(text="Hotkey:  -")
            status.config(text="Pick at least one modifier key.")
            return False

    def save():
        if refresh():
            config.save_hotkey(current())
            root.destroy()

    def reset():
        d_mods, d_key = config.parse(config.default_hotkey())
        for m, v in mod_vars.items():
            v.set(m in d_mods)
        key_var.set(d_key)
        refresh()

    if system.WAYLAND:
        ttk.Label(frm, wraplength=360, foreground="#555",
                  text="Wayland blocks global hotkeys. Set the shortcut in your system's keyboard "
                       "settings instead (command: ArabicLayoutFixer --once).").grid(
            row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))

    buttons = ttk.Frame(frm)
    buttons.grid(row=7, column=0, columnspan=4, sticky="e", pady=(16, 0))
    ttk.Button(buttons, text="Reset", command=reset).grid(row=0, column=0, padx=4)
    ttk.Button(buttons, text="Cancel", command=root.destroy).grid(row=0, column=1, padx=4)
    ttk.Button(buttons, text="Save", command=save).grid(row=0, column=2, padx=4)

    refresh()
    root.lift()
    root.attributes("-topmost", True)
    root.after(300, lambda: root.attributes("-topmost", False))
    root.mainloop()
