# Security

Arabic Layout Fixer runs locally. It has no network code, no telemetry, and never writes the text
you select to disk or to its log.

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
