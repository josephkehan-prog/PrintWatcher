# PrintWatcher

Auto-print files dropped into a OneDrive folder. Share a PDF from your iPad → it prints on your Windows desktop. No auth, no HTTPS, no port forwarding — the cloud provider handles sync, a tiny Python watcher handles printing.

## How it works

```
iPad (Share → Save to Files → OneDrive/PrintInbox)
        │
        ▼
  OneDrive sync
        │
        ▼
  Windows: watchdog detects new file
        │
        ▼
  SumatraPDF portable prints silently
        │
        ▼
  File moves to _printed/
```

~60 lines of Python. Tray icon for pause/resume. Auto-starts at login via Task Scheduler.

## Supported file types

`.pdf`, `.png`, `.jpg`, `.jpeg` — anything SumatraPDF can render.

## Requirements

- Windows 10 or 11
- Python 3.10+ (installed with "Add to PATH")
- OneDrive signed in (or iCloud Drive / Dropbox — just edit `WATCH_DIR`)
- A default printer configured

## Install

Open PowerShell (not admin) in the repo folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\bootstrap.ps1
```

The bootstrap will:
1. Install Python packages (`watchdog`, `pystray`, `pillow`)
2. Download SumatraPDF portable to `C:\Tools\SumatraPDF\`
3. Create `<OneDrive>\PrintInbox\`
4. Patch `print_watcher_tray.py` with your machine's paths
5. Register the `PrintWatcher` scheduled task
6. Start the watcher

Look for a printer icon near the clock — green = active, red = paused.

## Use

**From the iPad:** Share any PDF → *Save to Files* → *OneDrive* → *PrintInbox*.
**From any device:** drop a file in `<OneDrive>\PrintInbox\`.

The file prints and moves to `_printed\`.

## Files

| File | Purpose |
|------|---------|
| `print_watcher.py` | Minimal CLI watcher (no tray icon) |
| `print_watcher_tray.py` | Tray-icon version with pause/resume |
| `print_watcher_ui.py` | Desktop window with live log, stats, manual rescan, and OneDrive-rename fallback |
| `bootstrap.ps1` | One-command installer for new machines |
| `PrintWatcher.xml` | Task Scheduler template (bootstrap regenerates it per-machine) |
| `README_NEW_LAPTOP.md` | Detailed setup notes |

## Desktop UI version

`print_watcher_ui.py` is a Tkinter window — handy for debugging, restricted machines where Task Scheduler is blocked, or if you just like seeing what's happening.

```powershell
python print_watcher_ui.py
```

It auto-discovers paths from `print_watcher_tray.py` (whatever `bootstrap.ps1` patched in), so no extra setup.

What it does differently from the tray version:

- **Live event log** — every queued/printing/done/error line, timestamped, scrollable
- **Stats** — printed, in queue, errors
- **Print options panel** — pick a target printer, set copies, choose duplex (long/short edge) and color, all applied to the next file the watcher prints
- **Persistent print history** — every job (success or failure) is recorded in a sortable table with time, file, status, printer, and the options that were applied. Stored in `%APPDATA%\PrintWatcher\history.json` and survives restarts (last 200 entries).
- **Tabbed Activity / History view** — switch between the live log and the historical table without leaving the window
- **Manual rescan button** — re-checks the inbox immediately
- **`on_moved` handler** — catches files OneDrive delivers via temp-file rename (which `on_created` misses)
- **5-second polling fallback** — picks up anything the OS event stream drops

### Stapling, hole-punching, and other finishing options

SumatraPDF's `-print-settings` doesn't expose finishing — there's no toggle for "staple top-left" or "two-hole punch". Two options that do work:

1. **Set them as the printer's default** in the driver: `Settings -> Printers & scanners -> <printer> -> Printing preferences -> Finishing` tab. Every job sent to that queue is then stapled.
2. **Create a second Windows printer** pointed at the same physical device with stapling baked in (e.g. `Printix - Office (Stapled)`). Pick that one from the UI's printer dropdown when you want stapled jobs; switch back for unstapled.

For Printix specifically, your IT can also expose "stapled" / "hole-punched" as separate Printix queues — those then show up as separate Windows printers, perfect for the dropdown.

To auto-start without admin rights (e.g. locked-down work machines where Task Scheduler can't launch MS Store Python), drop a shortcut into `shell:startup`:

```powershell
$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut("$([Environment]::GetFolderPath('Startup'))\PrintWatcher.lnk")
$sc.TargetPath       = (Get-Command pythonw).Source
$sc.Arguments        = "`"$PWD\print_watcher_ui.py`""
$sc.WorkingDirectory = "$PWD"
$sc.WindowStyle      = 7
$sc.Save()
```

## Uninstall

```powershell
schtasks /Delete /TN "PrintWatcher" /F
Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process
Remove-Item -Recurse "C:\Tools\SumatraPDF"
```

## License

MIT
