# PrintWatcher bootstrap — run once on a new laptop.
# Usage (PowerShell, as your normal user — NOT admin):
#   cd <folder-containing-this-script>
#   Set-ExecutionPolicy -Scope Process Bypass -Force
#   .\bootstrap.ps1

$ErrorActionPreference = "Stop"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$UserName    = $env:USERNAME
$UserProfile = $env:USERPROFILE
$OneDriveDir = if ($env:OneDrive) { $env:OneDrive } else { Join-Path $UserProfile "OneDrive" }
$InboxDir    = Join-Path $OneDriveDir "PrintInbox"
$SumatraDir  = "C:\Tools\SumatraPDF"
$SumatraExe  = Join-Path $SumatraDir "SumatraPDF.exe"
$WatcherPy   = Join-Path $ScriptDir "print_watcher_tray.py"
$XmlPath     = Join-Path $ScriptDir "PrintWatcher.generated.xml"

Write-Host "=== PrintWatcher bootstrap ===" -ForegroundColor Cyan
Write-Host "User:       $UserName"
Write-Host "OneDrive:   $OneDriveDir"
Write-Host "Inbox:      $InboxDir"
Write-Host "Script dir: $ScriptDir"

# 1. Python check
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw "Python not found on PATH. Install Python 3.x from python.org first." }
$pythonw = Get-Command pythonw -ErrorAction SilentlyContinue
if (-not $pythonw) { throw "pythonw.exe not found on PATH." }
Write-Host "Python:     $($python.Source)"
Write-Host "Pythonw:    $($pythonw.Source)"

# 2. pip install deps
Write-Host "`n[1/5] Installing Python packages..." -ForegroundColor Yellow
python -m pip install --quiet --upgrade pip | Out-Null
python -m pip install --quiet watchdog pystray pillow
if ($LASTEXITCODE -ne 0) { throw "pip install failed." }

# 3. SumatraPDF
Write-Host "[2/5] Installing SumatraPDF portable..." -ForegroundColor Yellow
if (-not (Test-Path $SumatraExe)) {
    New-Item -ItemType Directory -Force -Path $SumatraDir | Out-Null
    $url = "https://www.sumatrapdfreader.org/dl/rel/3.5.2/SumatraPDF-3.5.2-64.exe"
    Invoke-WebRequest -Uri $url -OutFile $SumatraExe -UseBasicParsing
}
Write-Host "  SumatraPDF at $SumatraExe"

# 4. Folders
Write-Host "[3/5] Creating inbox folder..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $InboxDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InboxDir "_printed") | Out-Null

# 5. Patch watcher script paths if needed (rewrites WATCH_DIR / SUMATRA constants in place)
Write-Host "[4/5] Patching watcher script paths..." -ForegroundColor Yellow
if (-not (Test-Path $WatcherPy)) { throw "print_watcher_tray.py not found next to bootstrap.ps1" }
$content = Get-Content $WatcherPy -Raw
$content = [regex]::Replace($content,
    'WATCH_DIR\s*=\s*Path\(r".*?"\)',
    "WATCH_DIR = Path(r`"$InboxDir`")")
$content = [regex]::Replace($content,
    'SUMATRA\s*=\s*Path\(r".*?"\)',
    "SUMATRA = Path(r`"$SumatraExe`")")
Set-Content -Path $WatcherPy -Value $content -Encoding UTF8

# 6. Generate Task Scheduler XML with this machine's values
Write-Host "[5/5] Registering scheduled task..." -ForegroundColor Yellow
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Watch OneDrive PrintInbox and auto-print new files via SumatraPDF.</Description>
    <URI>\PrintWatcher</URI>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>$UserName</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$($pythonw.Source)</Command>
      <Arguments>"$WatcherPy"</Arguments>
      <WorkingDirectory>$ScriptDir</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

# Task Scheduler requires UTF-16 LE with BOM for XML import
$utf16 = New-Object System.Text.UnicodeEncoding $false, $true
[System.IO.File]::WriteAllText($XmlPath, $xml, $utf16)

schtasks /Create /XML $XmlPath /TN "PrintWatcher" /F | Out-Null
if ($LASTEXITCODE -ne 0) { throw "schtasks /Create failed." }
schtasks /Run /TN "PrintWatcher" | Out-Null

Start-Sleep -Seconds 3
$proc = Get-Process pythonw -ErrorAction SilentlyContinue
Write-Host "`n=== Done ===" -ForegroundColor Green
if ($proc) {
    Write-Host "PrintWatcher is running (pythonw PID: $($proc.Id -join ', '))."
    Write-Host "Look for the printer icon in your system tray (click ^ to show hidden icons)."
} else {
    Write-Warning "Task registered but pythonw not detected. Check: schtasks /Query /TN PrintWatcher /V /FO LIST"
}
Write-Host "`nTest it: drop a PDF into $InboxDir"
Write-Host "iPad:    Share -> Save to Files -> OneDrive -> PrintInbox"
