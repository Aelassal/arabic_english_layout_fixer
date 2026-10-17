# Security

Arabic Layout Fixer runs locally. It has no network code and no telemetry, and it never writes the text
you select to its log. The one thing kept on disk is the **last conversion**, so the hotkey can undo it: it is
stored in the settings folder (owner-only permissions), replaced on every fix, and deleted after 10 minutes.

On Windows and macOS the selected text briefly passes through the system clipboard. If you use Windows
Clipboard History or cloud clipboard, or a clipboard-manager app, they may record it. Turn them off before
fixing sensitive text such as passwords or keys.

## Reporting a vulnerability

Please report it privately through GitHub:
**Security tab → "Report a vulnerability"** on this repository.
Don't open a public issue for security problems. You'll get a reply within a few days.

## Verifying a download

Each release includes `SHA256SUMS.txt`. Compare it with your download:

- Windows (PowerShell): `Get-FileHash .\ArabicLayoutFixer-Windows.exe -Algorithm SHA256`
- macOS / Linux: `shasum -a 256 <file>`

The builds are produced by the public GitHub Actions workflow in `.github/workflows/build.yml`.
They are not code-signed yet, so Windows and macOS will show an "unknown publisher" warning.
