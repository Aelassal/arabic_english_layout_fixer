#!/bin/sh
# Arabic Layout Fixer installer for macOS and Linux. No admin rights needed.
#   install:    curl -fsSL https://raw.githubusercontent.com/Aelassal/arabic_english_layout_fixer/main/install.sh | sh
#   uninstall:  curl -fsSL https://raw.githubusercontent.com/Aelassal/arabic_english_layout_fixer/main/install.sh | sh -s -- --uninstall
# It downloads the file from the project's GitHub release, checks it against SHA256SUMS.txt,
# and installs it for the current user only. Read it before you run it.
set -eu

REPO="Aelassal/arabic_english_layout_fixer"
BASE="${LAYOUTFIX_BASE_URL:-https://github.com/$REPO/releases/latest/download}"
APP_ID="com.aelassal.arabiclayoutfixer"

say()  { printf '%s\n' "$*"; }
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

download() {  # download URL DEST
    if have curl; then curl -fsSL "$1" -o "$2"
    elif have wget; then wget -q "$1" -O "$2"
    else fail "curl or wget is required"; fi
}

sha256_of() {
    if have sha256sum; then sha256sum "$1" | cut -d' ' -f1
    elif have shasum; then shasum -a 256 "$1" | cut -d' ' -f1
    else fail "sha256sum or shasum is required to verify the download"; fi
}

# fetch NAME DEST: download a release file and verify its checksum
fetch_verified() {
    name="$1"; dest="$2"
    download "$BASE/$name" "$dest"
    download "$BASE/SHA256SUMS.txt" "$TMP/SHA256SUMS.txt"
    want=$(awk -v f="$name" '$2 == f || $2 == "*" f { print $1 }' "$TMP/SHA256SUMS.txt")
    [ -n "$want" ] || fail "no checksum listed for $name"
    got=$(sha256_of "$dest")
    [ "$want" = "$got" ] || fail "checksum mismatch for $name (expected $want, got $got); nothing was installed"
    say "Checksum OK."
}

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

OS=$(uname -s)
ARCH=$(uname -m)

# ---------------------------------------------------------------- Linux
GNOME_KEYS="org.gnome.settings-daemon.plugins.media-keys"
GNOME_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/arabic-layout-fixer/"

linux_uninstall() {
    pkill -x ArabicLayoutFixer-Linux 2>/dev/null || true
    rm -rf "$HOME/.local/share/arabic-layout-fixer"
    rm -f "$HOME/.local/bin/arabic-layout-fixer" \
          "$HOME/.local/share/applications/arabic-layout-fixer.desktop" \
          "$HOME/.config/autostart/arabic-layout-fixer.desktop"
    if have gsettings && [ -z "${LAYOUTFIX_NO_SHORTCUT:-}" ]; then
        cur=$(gsettings get $GNOME_KEYS custom-keybindings 2>/dev/null || true)
        case "$cur" in
            *"$GNOME_PATH"*)
                new=$(printf '%s' "$cur" | sed "s#, '$GNOME_PATH'##; s#'$GNOME_PATH', ##; s#'$GNOME_PATH'##")
                [ "$new" = "[]" ] && new="@as []"
                gsettings set $GNOME_KEYS custom-keybindings "$new" || true ;;
        esac
    fi
    say "Arabic Layout Fixer was removed. Its settings are kept in ~/.config/arabic-layout-fixer (delete it if you like)."
}

add_gnome_shortcut() {  # add_gnome_shortcut BIN
    have gsettings || return 1
    gsettings list-schemas 2>/dev/null | grep -qx "$GNOME_KEYS" || return 1
    cur=$(gsettings get $GNOME_KEYS custom-keybindings 2>/dev/null) || return 1
    case "$cur" in
        *"$GNOME_PATH"*) ;;
        "@as []"|"[]") gsettings set $GNOME_KEYS custom-keybindings "['$GNOME_PATH']" ;;
        *) gsettings set $GNOME_KEYS custom-keybindings "$(printf '%s' "$cur" | sed "s#\]\$#, '$GNOME_PATH']#")" ;;
    esac
    slot="$GNOME_KEYS.custom-keybinding:$GNOME_PATH"
    gsettings set "$slot" name "Arabic Layout Fixer"
    gsettings set "$slot" command "$1 --once"
    gsettings set "$slot" binding "<Control><Alt>a"
}

linux_install() {
    case "$ARCH" in x86_64|amd64) ;; *) fail "the Linux build is for x86_64 only (this is $ARCH). Run it from source instead, see the README." ;; esac
    dir="$HOME/.local/share/arabic-layout-fixer"
    bin="$dir/ArabicLayoutFixer-Linux"
    mkdir -p "$dir" "$HOME/.local/bin" "$HOME/.local/share/applications"

    say "Downloading Arabic Layout Fixer for Linux..."
    fetch_verified ArabicLayoutFixer-Linux "$TMP/app"
    chmod +x "$TMP/app"
    pkill -x ArabicLayoutFixer-Linux 2>/dev/null || true
    mv -f "$TMP/app" "$bin"
    ln -sf "$bin" "$HOME/.local/bin/arabic-layout-fixer"

    if [ -f "$dir/icon.png" ]; then :; else
        download "https://raw.githubusercontent.com/$REPO/main/assets/icon.png" "$dir/icon.png" 2>/dev/null || true
    fi
    cat > "$HOME/.local/share/applications/arabic-layout-fixer.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Arabic Layout Fixer
Comment=Fix text typed with the wrong keyboard layout
Exec="$bin"
Icon=$dir/icon.png
Terminal=false
Categories=Utility;
DESKTOP

    wayland=no
    [ "${XDG_SESSION_TYPE:-}" = "wayland" ] && wayland=yes

    if [ "$wayland" = yes ]; then
        say ""
        say "You are on Wayland, which blocks global hotkeys, so a system shortcut is used instead."
        if [ -z "${LAYOUTFIX_NO_SHORTCUT:-}" ] && add_gnome_shortcut "$bin"; then
            say "Added the GNOME shortcut Ctrl+Alt+A (change it in Settings > Keyboard > Custom Shortcuts)."
        else
            say "Add a custom shortcut in your desktop's keyboard settings that runs:"
            say "    $bin --once"
        fi
        if ! have ydotool; then
            say ""
            say "One more step: pasting on Wayland needs ydotool. Install it, for example:"
            say "    sudo apt install ydotool        # Debian / Ubuntu"
            say "    sudo dnf install ydotool        # Fedora"
            say "and make sure the ydotoold service is running (see the README)."
        fi
    else
        mkdir -p "$HOME/.config/autostart"
        cat > "$HOME/.config/autostart/arabic-layout-fixer.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Arabic Layout Fixer
Exec="$bin"
X-GNOME-Autostart-enabled=true
DESKTOP
        if [ -z "${LAYOUTFIX_NO_START:-}" ]; then
            nohup "$bin" >/dev/null 2>&1 &
            say "Started. It also starts with your computer. Hotkey: Ctrl+Alt+A."
        fi
    fi
    say ""
    say "Done. Select some text and press Ctrl+Alt+A."
}

# ---------------------------------------------------------------- macOS
mac_uninstall() {
    pkill -x ArabicLayoutFixer 2>/dev/null || true
    rm -rf "$HOME/Applications/ArabicLayoutFixer.app"
    rm -f "$HOME/Library/LaunchAgents/$APP_ID.plist"
    say "Arabic Layout Fixer was removed. Settings stay in ~/Library/Application Support/ArabicLayoutFixer (delete it if you like)."
}

mac_install() {
    case "$ARCH" in
        arm64) file="ArabicLayoutFixer-macOS-AppleSilicon.dmg" ;;
        x86_64) file="ArabicLayoutFixer-macOS-Intel.dmg" ;;
        *) fail "unsupported Mac processor: $ARCH" ;;
    esac
    say "Downloading Arabic Layout Fixer for macOS ($ARCH)..."
    fetch_verified "$file" "$TMP/app.dmg"

    mnt="$TMP/mnt"; mkdir -p "$mnt"
    hdiutil attach -nobrowse -readonly -quiet -mountpoint "$mnt" "$TMP/app.dmg"
    trap 'hdiutil detach -quiet "$mnt" 2>/dev/null || true; rm -rf "$TMP"' EXIT INT TERM
    [ -d "$mnt/ArabicLayoutFixer.app" ] || fail "the disk image does not contain the app"

    pkill -x ArabicLayoutFixer 2>/dev/null || true
    mkdir -p "$HOME/Applications"
    rm -rf "$HOME/Applications/ArabicLayoutFixer.app"
    cp -R "$mnt/ArabicLayoutFixer.app" "$HOME/Applications/"
    # a file fetched by curl is not quarantined, but clear the flag in case it is
    xattr -dr com.apple.quarantine "$HOME/Applications/ArabicLayoutFixer.app" 2>/dev/null || true

    say "Installed to ~/Applications."
    if [ -z "${LAYOUTFIX_NO_START:-}" ]; then
        open "$HOME/Applications/ArabicLayoutFixer.app"
    fi
    say ""
    say "Last step (macOS asks you, I can't do it for you):"
    say "  System Settings > Privacy & Security > Accessibility, and Input Monitoring:"
    say "  switch on Arabic Layout Fixer. Then select text and press Ctrl+Shift+A."
    say "  To start it with your Mac: click its menu-bar icon > Start with computer."
}

# ---------------------------------------------------------------- main
UNINSTALL=no
[ "${1:-}" = "--uninstall" ] && UNINSTALL=yes

case "$OS" in
    Linux)  if [ $UNINSTALL = yes ]; then linux_uninstall; else linux_install; fi ;;
    Darwin) if [ $UNINSTALL = yes ]; then mac_uninstall; else mac_install; fi ;;
    *) fail "this script is for macOS and Linux. On Windows use install.ps1 (see the README)." ;;
esac
