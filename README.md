# Arabic Layout Fixer

Typed in Arabic by mistake (or English with the Arabic layout on)? Select the text, press
**Ctrl + Alt + A** (changeable in Settings), and it is replaced with what you meant to type.
Works in both directions and picks the direction automatically. Free and open source.

![Demo: Arabic typed by mistake is fixed with one hotkey](assets/demo.gif)

`اثممخ` → `hello` &nbsp;·&nbsp; `hello` → `اثممخ`

Press the hotkey again on the converted text (within 10 minutes) to **undo** it.

## Install
Download the file for your system from **Releases**. Each release also lists SHA256 checksums
(`SHA256SUMS.txt`) so you can verify the download.

- **Windows:** run `ArabicLayoutFixer-Windows.exe`. SmartScreen may warn "unknown publisher" because the
  app is not code-signed: click *More info → Run anyway*.
- **macOS:** open the `.dmg` (Apple Silicon or Intel), drag the app to *Applications* and open it. The first
  time macOS blocks it: open *System Settings → Privacy & Security* and click **Open Anyway**. Then allow it under
  *Privacy & Security → Accessibility* and *Input Monitoring*. Because the app is not notarized, macOS may ask
  again after an update. Default hotkey on Mac: **Ctrl + Shift + A**.
- **Linux (X11):** install `xclip`, then run `ArabicLayoutFixer-Linux`.
- **Linux (Wayland, e.g. GNOME):** the desktop blocks global hotkeys, so use a system shortcut instead. Install
  `wl-clipboard` and `ydotool` (the `ydotoold` service must be running), then add a custom shortcut
  (GNOME: Settings → Keyboard → Custom Shortcuts) that runs `ArabicLayoutFixer-Linux --once`.

A green swap-arrows icon appears in the tray / menu bar. Click it for **Settings...** and **Start with computer**.
On GNOME the tray icon needs the AppIndicator extension; the hotkey works without it.

## How it behaves
- It converts the **highlighted** text and pastes the result over it. On Windows and macOS it copies with
  Ctrl/Cmd+C (Ctrl+Insert on Windows) and pastes with Ctrl/Cmd+V (Shift+Insert on Windows).
  Linux reads the highlighted text directly and pastes with Shift+Insert.
- **Your clipboard is put back** afterwards. If the clipboard holds an image or files, Linux restores them;
  on Windows and macOS the app refuses to run and tells you, so nothing is lost.
- In a terminal the fixed text is pasted at the cursor (a terminal cannot replace highlighted output).
- Nothing is sent anywhere. The app has no network code. It does not log or store what you type, except the
  last conversion (kept for 10 minutes, in your settings folder) so the hotkey can undo it.
- Problems are written to a log file in the settings folder (`%APPDATA%\ArabicLayoutFixer`,
  `~/Library/Application Support/ArabicLayoutFixer` or `~/.config/arabic-layout-fixer`).

## Change the hotkey
Tray icon → **Settings...**, tick the modifier keys (Ctrl, Alt, Win/Cmd; Shift alone is not allowed),
pick a key, press **Save**. It takes effect immediately.

<img src="assets/settings.png" width="328" alt="Settings window">

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
