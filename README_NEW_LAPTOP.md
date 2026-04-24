# PrintWatcher — New Laptop Setup

## What to copy
Copy this folder to the new laptop (USB or OneDrive). Only two files are strictly required:
- `print_watcher_tray.py`
- `bootstrap.ps1`

## Prerequisites on the new laptop
- Windows 10/11
- **Python 3.10+** installed from python.org (tick "Add Python to PATH" during install)
- **OneDrive** signed in and syncing (or iCloud/Dropbox — see note below)
- A default printer configured (`Settings → Bluetooth & devices → Printers & scanners`)

## Setup (one command)
Open **PowerShell** (not admin) in the folder containing these files, then:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\bootstrap.ps1
```

The script will:
1. Install Python packages: `watchdog`, `pystray`, `pillow`
2. Download SumatraPDF portable to `C:\Tools\SumatraPDF\`
3. Create `<OneDrive>\PrintInbox\` (auto-detects your OneDrive location)
4. Patch `print_watcher_tray.py` with the new machine's paths
5. Register the `PrintWatcher` scheduled task (auto-start at login)
6. Launch the watcher — tray icon appears near the clock

## Test
Drop a PDF into `<OneDrive>\PrintInbox\`. It should print and move to `_printed\`.

On iPad: Share any PDF → **Save to Files** → **OneDrive** → **PrintInbox**.

## Tray icon
Right-click the printer icon in the system tray:
- **Pause / Resume** — toggle without quitting
- **Open Inbox Folder** — jump to the folder in Explorer
- **Quit** — stop the watcher (relaunch with `schtasks /Run /TN PrintWatcher`)

## Uninstall
```powershell
schtasks /Delete /TN "PrintWatcher" /F
Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process
Remove-Item -Recurse "C:\Tools\SumatraPDF"
```

## Using iCloud or Dropbox instead of OneDrive
Edit `print_watcher_tray.py` after running bootstrap — change `WATCH_DIR` to point at the cloud folder you prefer, then restart the task:
```powershell
schtasks /End /TN "PrintWatcher"; schtasks /Run /TN "PrintWatcher"
```
