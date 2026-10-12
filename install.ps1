# Arabic Layout Fixer installer for Windows. No admin rights needed.
#   install:    irm https://raw.githubusercontent.com/Aelassal/arabic_english_layout_fixer/main/install.ps1 | iex
#   uninstall:  $env:LAYOUTFIX_UNINSTALL=1; irm https://raw.githubusercontent.com/Aelassal/arabic_english_layout_fixer/main/install.ps1 | iex
# It downloads the exe from the project's GitHub release, checks it against SHA256SUMS.txt and
# installs it for the current user only. Read it before you run it.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Repo    = 'Aelassal/arabic_english_layout_fixer'
$Base    = if ($env:LAYOUTFIX_BASE_URL) { $env:LAYOUTFIX_BASE_URL } else { "https://github.com/$Repo/releases/latest/download" }
$Name    = 'ArabicLayoutFixer'
$Dir     = Join-Path $env:LOCALAPPDATA $Name
$Exe     = Join-Path $Dir "$Name.exe"
$Link    = Join-Path ([Environment]::GetFolderPath('Programs')) 'Arabic Layout Fixer.lnk'
$RunKey  = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'

# Download with a visible progress bar and a stall timeout. curl.exe ships with Windows 10/11;
# Invoke-WebRequest is the fallback.
function Get-File($Url, $Dest) {
    for ($i = 1; $i -le 3; $i++) {
        $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
        if ($curl) {
            & $curl.Source -L --fail --show-error --connect-timeout 20 --speed-limit 2000 --speed-time 30 --progress-bar -o $Dest $Url
            if ($LASTEXITCODE -eq 0 -and (Test-Path $Dest)) { return }
        } else {
            try { Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing -TimeoutSec 120; return } catch { Write-Host $_.Exception.Message }
        }
        if ($i -lt 3) { Write-Host "Download failed or stalled, retrying ($i of 3)..."; Start-Sleep -Seconds 2 }
    }
    throw "could not download $Url (check your internet connection, VPN or proxy)"
}

function Stop-App { Get-Process -Name $Name -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep -Milliseconds 500 }

if ($env:LAYOUTFIX_UNINSTALL) {
    Stop-App
    Remove-ItemProperty -Path $RunKey -Name $Name -ErrorAction SilentlyContinue
    Remove-Item $Link -Force -ErrorAction SilentlyContinue
    Remove-Item $Dir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Arabic Layout Fixer was removed. Settings stay in $env:APPDATA\$Name (delete that folder if you like)."
    return
}

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("alf-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    Write-Host 'Downloading Arabic Layout Fixer for Windows (about 11 MB; on a slow connection this can take several minutes)...'
    $file = 'ArabicLayoutFixer-Windows.zip'
    Get-File "$Base/$file" (Join-Path $tmp $file)
    Get-File "$Base/SHA256SUMS.txt" (Join-Path $tmp 'SHA256SUMS.txt')

    $line = Get-Content (Join-Path $tmp 'SHA256SUMS.txt') | Where-Object { $_ -match "\s\*?$([regex]::Escape($file))$" } | Select-Object -First 1
    if (-not $line) { throw "no checksum listed for $file" }
    $want = ($line -split '\s+')[0].ToLower()
    $got  = (Get-FileHash (Join-Path $tmp $file) -Algorithm SHA256).Hash.ToLower()
    if ($want -ne $got) { throw "checksum mismatch (expected $want, got $got); nothing was installed" }
    Write-Host 'Checksum OK.'

    Stop-App
    $unpacked = Join-Path $tmp 'unpacked'
    Expand-Archive -Path (Join-Path $tmp $file) -DestinationPath $unpacked -Force
    if (-not (Test-Path (Join-Path $unpacked "$Name.exe"))) { throw 'the download does not contain the app' }
    if (Test-Path $Dir) { Remove-Item $Dir -Recurse -Force }
    New-Item -ItemType Directory -Path $Dir -Force | Out-Null
    Move-Item (Join-Path $unpacked '*') $Dir -Force
    Get-ChildItem $Dir -Recurse -File | Unblock-File -ErrorAction SilentlyContinue

    # Start menu entry, and start with Windows
    $sh = New-Object -ComObject WScript.Shell
    $lnk = $sh.CreateShortcut($Link)
    $lnk.TargetPath = $Exe
    $lnk.WorkingDirectory = $Dir
    $lnk.Save()
    if (-not (Test-Path $RunKey)) { New-Item -Path $RunKey -Force | Out-Null }
    New-ItemProperty -Path $RunKey -Name $Name -Value ('"' + $Exe + '"') -PropertyType String -Force | Out-Null

    if (-not $env:LAYOUTFIX_NO_START) { Start-Process -FilePath $Exe }
    Write-Host ''
    Write-Host 'Done. Look for the green icon in the tray (click ^ if it is hidden).'
    Write-Host 'Select some text and press Ctrl+Alt+A. It also starts with Windows.'
    Write-Host 'If Windows shows "unknown publisher" (the app is not code-signed yet), choose More info > Run anyway.'
}
finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
