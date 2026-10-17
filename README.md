# Arabic Layout Fixer

Typed in Arabic by mistake (or English with the Arabic layout on)? Select the text, press
**Ctrl + Alt + A** (changeable in Settings), and it is replaced with what you meant to type.
Works in both directions and picks the direction automatically. Free and open source.

![Demo: Arabic typed by mistake is fixed with one hotkey](https://raw.githubusercontent.com/Aelassal/arabic_english_layout_fixer/main/assets/demo.gif)

`اثممخ` → `hello` &nbsp;·&nbsp; `hello` → `اثممخ`

Press the hotkey again on the converted text (within 10 minutes) to **undo** it.

## Install

**One line** (installs for your user only, no admin rights, and checks the download against the published
SHA256 checksum before installing):

| System | Paste this |
|---|---|
| Windows (PowerShell) | `irm https://raw.githubusercontent.com/Aelassal/arabic_english_layout_fixer/main/install.ps1 \| iex` |
| macOS (Terminal) | `curl -fsSL https://raw.githubusercontent.com/Aelassal/arabic_english_layout_fixer/main/install.sh \| sh` |
| Linux (terminal) | `curl -fsSL https://raw.githubusercontent.com/Aelassal/arabic_english_layout_fixer/main/install.sh \| sh` |

The scripts are short, so you can read [install.sh](https://github.com/Aelassal/arabic_english_layout_fixer/blob/main/install.sh) and [install.ps1](https://github.com/Aelassal/arabic_english_layout_fixer/blob/main/install.ps1) first.
To remove the app, run the same line with `--uninstall` (macOS/Linux: `... \| sh -s -- --uninstall`) or, on
Windows, `$env:LAYOUTFIX_UNINSTALL=1` before it.

**Or with Python** (a tiny download from PyPI, the same on all three systems; also avoids the
"unknown publisher" prompt, because nothing unsigned is run):
```
pipx install arabic-layout-fixer      # or: pip install arabic-layout-fixer
arabic-layout-fixer-tray              # starts the tray app (no console window on Windows)
```
On Linux the Settings window needs Tk: `sudo apt install python3-tk` (Debian/Ubuntu) or `sudo dnf install python3-tkinter`.

**Or download by hand** from **Releases**. Each release also lists SHA256 checksums (`SHA256SUMS.txt`).

- **Windows:** run `ArabicLayoutFixer-Windows.exe` (one file, about 11 MB; `ArabicLayoutFixer-Windows.zip` is the same
  app as a folder, which starts faster). The app is not code-signed, so SmartScreen may warn "unknown publisher":
  click *More info → Run anyway*. If **Smart App Control** is switched on (Windows Security → App & browser control),
  Windows blocks unsigned programs with no way to override; use the Python install above instead (Python itself is
  signed), or wait for a signed release.
  The app cannot type into windows that run **as administrator** (Windows blocks it); the fix then does nothing.
- **macOS:** open the `.dmg` (Apple Silicon or Intel), drag the app to *Applications* and open it. The first
  time macOS blocks it: open *System Settings → Privacy & Security* and click **Open Anyway**. Then allow it under
  *Privacy & Security → Accessibility* and *Input Monitoring*. Because the app is not notarized, macOS may ask
  again after an update. The one-line installer downloads with `curl`, which macOS does not flag, so Gatekeeper's
  usual check does not run for it: only use it if you trust this repository (read `install.sh` first). Default hotkey on Mac: **Ctrl + Shift + A**.
- **Linux (X11):** run `ArabicLayoutFixer-Linux` (one file, about 12 MB; `ArabicLayoutFixer-Linux.tar.gz` is the same app as a folder, which starts faster). Nothing else is needed (`xclip` is only used as a fallback).
- **Linux (Wayland, e.g. GNOME):** the desktop blocks global hotkeys, so use a system shortcut instead. Install
  `ydotool` (the `ydotoold` service must be running), then add a custom shortcut
  (GNOME: Settings → Keyboard → Custom Shortcuts) that runs `ArabicLayoutFixer-Linux --once`.
  (The one-line installer adds the GNOME shortcut Ctrl+Alt+A for you.)
  The clipboard is handled through XWayland (on by default in GNOME; `DISPLAY` must be set for the shortcut),
  so no helper programs run and no window ever opens. If XWayland is disabled, `wl-clipboard` is used as a
  fallback; note that on GNOME each `wl-copy`/`wl-paste` call opens a tiny window to get focus, which makes
  the dock flicker.

A green swap-arrows icon appears in the tray / menu bar. Click it for **Settings...** and **Start with computer**.
On GNOME the tray icon needs the AppIndicator extension; the hotkey works without it.

## How it behaves
- It converts the **highlighted** text and pastes the result over it. On Windows and macOS it copies with
  Ctrl/Cmd+C (Ctrl+Insert on Windows) and pastes with Ctrl/Cmd+V (Shift+Insert on Windows).
  Linux reads the highlighted text directly and pastes with Shift+Insert.
- **Your clipboard is put back** afterwards. If the clipboard holds an image or files, Linux restores them;
  on Windows and macOS the app refuses to run and tells you, so nothing is lost.
- In a terminal the fixed text is pasted at the cursor (a terminal cannot replace highlighted output).
- On Linux the paste key goes out about 0.25 s after the hotkey press (so the hotkey is released first) and the
  clipboard is put back as soon as the app has read the text. If no app has read the text after 0.6 s (the paste
  key was swallowed, e.g. because a hotkey key was still held), the text is offered again and the paste key is
  sent once more; it is never sent again once the app has read the text, so nothing is pasted twice. A small
  background process keeps serving the restored clipboard until you copy something else, like `wl-copy` would.
- On Windows and macOS the selected text briefly passes through the system clipboard, so Windows Clipboard History / cloud
  clipboard or a clipboard-manager app may record it. Turn them off before fixing sensitive text (passwords, keys).
- Nothing is sent anywhere. The app has no network code. It does not log or store what you type, except the
  last conversion (kept for 10 minutes, in your settings folder) so the hotkey can undo it.
- Problems are written to a log file in the settings folder (`%APPDATA%\ArabicLayoutFixer`,
  `~/Library/Application Support/ArabicLayoutFixer` or `~/.config/arabic-layout-fixer`). On Linux each fix
  logs a timeline from the hotkey press (process start) to the clipboard restore: lengths, timings and which
  window asked for the text (an X11 window id), never the text itself.

## Change the hotkey
Tray icon → **Settings...**, tick the modifier keys (Ctrl, Alt, Win/Cmd; Shift alone is not allowed),
pick a key, press **Save**. It takes effect immediately.

The fix starts when you **let go** of the hotkey, not when you press it. The app then sends its own keys
(copy, paste) with none of your hotkey's keys still held down, which is what makes it work reliably in browsers,
Electron apps and chat boxes. If you keep holding the keys, it simply waits.

**Recommended if the fix ever fails to paste: use a function key on its own**, for example **F8**
(F1-F12 are allowed). It has no modifier that can be held down, so it is the most reliable choice. In Settings,
untick every modifier, pick the key and save. Apps still see that key too, so choose one you do not use
(Excel's F9 recalculates, for example).
On Linux with Wayland (GNOME) you set the key in *Settings → Keyboard → Custom Shortcuts* instead, or run:
```
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/arabic-layout-fixer/ binding 'F8'
```
The default stays Ctrl + Alt + A (Ctrl + Shift + A on macOS).

<img src="https://raw.githubusercontent.com/Aelassal/arabic_english_layout_fixer/main/assets/settings.png" width="328" alt="Settings window">

## Run from source
```
pip install .
arabic-layout-fixer           # tray app (or: python -m layoutfix)
python -m layoutfix --once    # fix the current selection once (for custom shortcuts)
python -m unittest discover -s tests
```

## Limitations
- Assumes the standard Arabic 101 layout.
- The key that types `لا` is read as `b`; a real `g` then `h` is ambiguous.
- Plain-symbol results such as `][/` cannot be converted back, since nothing marks them as Arabic.
- If nothing is highlighted on Linux, an older highlight may still be the "current selection".
- Rich formatting (bold, links) is not kept in the converted text, and may be lost from the clipboard
  on Windows/macOS when it held formatted text.
- Not code-signed or notarized yet.
