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
- **Persistent print history** — every job (success or failure) is recorded in a sortable table with time, submitter, file, status, printer, and the options that were applied. Stored in `%APPDATA%\PrintWatcher\history.json` and survives restarts (last 200 entries).
- **Multi-user submitter tracking** — files dropped into the inbox root attribute to the current Windows user. Files dropped into a subfolder (`PrintInbox\MaryDoe\report.pdf`) attribute to that subfolder name. The History tab shows the submitter column, and printed files move into matching `_printed\<submitter>\` subfolders. Useful when several staff share a OneDrive inbox.
- **Tabbed Activity / History view** — switch between the live log and the historical table without leaving the window
- **Interactive history** — live filter box, right-click any row for **Reprint** (copies the archived file back into the inbox), **Open file**, **Show in folder**, **Filter to this submitter / printer**, **Copy filename**. Double-click a row to open the file.
- **Manual rescan button** — re-checks the inbox immediately
- **`on_moved` handler** — catches files OneDrive delivers via temp-file rename (which `on_created` misses)
- **5-second polling fallback** — picks up anything the OS event stream drops, walking subfolders too

## Diagnostics: `scripts/verify_environment.py`

When something's not working, the fastest path to a fix is:

```powershell
python scripts\verify_environment.py
```

Outputs PASS / WARN / FAIL for: Python version, MS Store Python alias detection, required packages (watchdog/pystray/pillow), SumatraPDF binary, OneDrive env vars, PrintInbox folder, default printer, Printix client process, and whether `bootstrap.ps1` has patched `print_watcher_tray.py`. Each non-PASS row includes a one-line `fix:` hint.

`--json` emits machine-readable output if you want to wire it into a setup pipeline.

## Per-job options from the iPad (filename conventions)

The desktop UI's "Print options" panel applies to every job until you change it. That's clunky from the iPad where you don't have the panel — so PrintWatcher also reads options encoded **in the filename or folder name** before printing. Two iPad-friendly paths:

### Path A — preset folders (no typing)

Create preset folders once, then just save into the right one from the iPad Files app:

```powershell
python scripts\setup_inbox_presets.py
```

Creates a starter set inside `PrintInbox\`:

```
__copies=30/         __duplex/         __duplex_mono/
__copies=15/         __mono/           __copies=30_duplex/
```

From iPad: Share PDF → **Save to Files** → drill into `OneDrive\PrintInbox\__copies=30\` → Save. Done — 30 copies print. No filename editing.

Add custom presets too: `python scripts\setup_inbox_presets.py __color __copies=5_duplex`

### Path B — encode in the filename (renaming on save)

If you don't want to commit to a preset, rename the file before saving from the share sheet:

```
worksheet__copies=30.pdf         -> 30 copies, otherwise UI defaults
report__duplex_mono.pdf          -> duplex (long edge), monochrome
quiz__copies=12_duplex_color.pdf -> 12 copies, duplex, color
notes.pdf                        -> uses whatever the desktop UI is set to
```

### Combining presets, submitters, and filenames

The watcher walks every path component from the inbox down. Each can carry an `__opts` block. Filename options apply last and win on conflicts.

```
PrintInbox/MaryDoe/doc.pdf                          -> submitter MaryDoe, UI defaults
PrintInbox/MaryDoe__duplex/doc.pdf                  -> submitter MaryDoe, duplex
PrintInbox/Class3__copies=30_duplex/doc.pdf         -> submitter Class3, 30 copies, duplex
PrintInbox/MaryDoe__duplex/doc__copies=2.pdf        -> submitter MaryDoe, duplex, 2 copies (filename overrides)
PrintInbox/MaryDoe/__copies=30/doc.pdf              -> submitter MaryDoe, 30 copies (nested preset)
```

Recognised tokens:

| Token | Effect |
|---|---|
| `copies=N` (or `n=N`, `x=N`), 1-99 | number of copies |
| `duplex`, `duplexlong`, `long` | duplex (long edge) |
| `duplexshort`, `short` | duplex (short edge) |
| `simplex`, `single` | force single-sided |
| `color`, `colour` | color print |
| `mono`, `monochrome`, `bw` | monochrome |

Out-of-range or unrecognised tokens are silently ignored. The original file path is **not** rewritten — `_printed/` archives keep whatever you dropped, and the History tab shows the merged options that were actually applied with a `path overrides:` trailer in the live log.

Printer choice can't be encoded — printer names usually contain spaces, which collide with the token separator. Set the printer once in the desktop UI dropdown.

### iPad Shortcut to make it one-tap

Apple Shortcuts (built-in iPad app) can pick a destination folder programmatically. Recipe:

1. **Shortcuts → New shortcut → Receive PDFs from Share Sheet**
2. **Choose from Menu** ("Which preset?") → list your preset folder names (e.g. `30 copies`, `Duplex mono`, `Class set (30 + duplex)`)
3. **If**/**Match** maps each menu choice to a folder name (`__copies=30`, `__duplex_mono`, `__copies=30_duplex`)
4. **Save File** → target `OneDrive\PrintInbox\<chosen folder>`

Now the share sheet has a one-tap "Print via PrintWatcher" entry → quick prompts → done.

## Companion scripts

Each is standalone and discovers your `PrintInbox` automatically by reading the same path that `bootstrap.ps1` patched into `print_watcher_tray.py`.

| Script | Purpose | Extra deps |
|---|---|---|
| `scripts/name_stamper.py` | Watches `PrintInbox\stamped\`, overlays a name/date/period stamp at top-right of every page, then forwards into the inbox | `pypdf`, `reportlab` |
| `scripts/roster_split.py` | Splits a multi-page packet PDF into one file per roster row (CSV); optional `--to-inbox` queues every split for printing | `pypdf` |
| `scripts/redact.py` | Crops header/footer bands off PDFs (one-shot or watch mode under `PrintInbox\redact\`) | `pypdf` |
| `scripts/email_to_inbox.py` | IMAP-polls a mailbox folder, saves PDF/image attachments from unread messages into the inbox; uses stdlib only, configured via env vars (`IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD`, `IMAP_FOLDER`) | none |
| `scripts/screenshot_to_print.py` | Watches a Screenshots folder, copies (or `--move`s) every new image into the inbox | none |
| `scripts/web_to_pdf.py` | Renders a URL to PDF via headless Edge/Chrome and drops it in the inbox; no Python rendering deps required | none (Edge/Chrome) |
| `scripts/setup_inbox_presets.py` | Pre-creates iPad-friendly preset folders inside `PrintInbox\` (`__copies=30`, `__duplex`, `__duplex_mono`, etc.) so the iPad Files-app workflow becomes pick-folder-and-save | none |

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
