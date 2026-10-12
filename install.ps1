# Arabic Layout Fixer installer for Windows. No admin rights needed.
#   install:    irm https://raw.githubusercontent.com/Aelassal/arabic_english_layout_fixer/main/install.ps1 | iex
#   uninstall:  $env:LAYOUTFIX_UNINSTALL=1; irm https://raw.githubusercontent.com/Aelassal/arabic_english_layout_fixer/main/install.ps1 | iex
# It downloads the exe from the project's GitHub release, checks it against SHA256SUMS.txt and
# installs it for the current user only. Read it before you run it.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = 'SilentlyContinue'    # makes Invoke-WebRequest much faster

$Repo    = 'Aelassal/arabic_english_layout_fixer'
$Base    = if ($env:LAYOUTFIX_BASE_URL) { $env:LAYOUTFIX_BASE_URL } else { "https://github.com/$Repo/releases/latest/download" }
$Name    = 'ArabicLayoutFixer'
$Dir     = Join-Path $env:LOCALAPPDATA $Name
$Exe     = Join-Path $Dir "$Name.exe"
$Link    = Join-Path ([Environment]::GetFolderPath('Programs')) 'Arabic Layout Fixer.lnk'
$RunKey  = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'

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
    Write-Host 'Downloading Arabic Layout Fixer for Windows...'
    $file = 'ArabicLayoutFixer-Windows.exe'
    Invoke-WebRequest -Uri "$Base/$file" -OutFile (Join-Path $tmp $file) -UseBasicParsing
    Invoke-WebRequest -Uri "$Base/SHA256SUMS.txt" -OutFile (Join-Path $tmp 'SHA256SUMS.txt') -UseBasicParsing

    $line = Get-Content (Join-Path $tmp 'SHA256SUMS.txt') | Where-Object { $_ -match "\s\*?$([regex]::Escape($file))$" } | Select-Object -First 1
    if (-not $line) { throw "no checksum listed for $file" }
    $want = ($line -split '\s+')[0].ToLower()
    $got  = (Get-FileHash (Join-Path $tmp $file) -Algorithm SHA256).Hash.ToLower()
    if ($want -ne $got) { throw "checksum mismatch (expected $want, got $got); nothing was installed" }
    Write-Host 'Checksum OK.'

    Stop-App
    New-Item -ItemType Directory -Path $Dir -Force | Out-Null
    Move-Item (Join-Path $tmp $file) $Exe -Force
    Unblock-File $Exe -ErrorAction SilentlyContinue

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
