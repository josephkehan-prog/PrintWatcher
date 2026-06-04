# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

PrintWatcher auto-prints files dropped into a cloud-synced folder (OneDrive/iCloud/Dropbox):
share a PDF from an iPad → it lands in `PrintInbox/` → a Windows watcher prints it via
portable SumatraPDF → the file moves to `_printed/`. Aimed at schools/teachers; ships as
standalone Windows `.exe`s (no Python required on the target machine).

It is mid-migration (v0.4). The UI is being ported from a legacy Tk/customtkinter desktop
app to a native **C# / WinUI 3 shell** that talks to a **headless Python backend** over
REST + WebSocket on `127.0.0.1`. Both UIs ship side-by-side through v0.5; v0.6 deletes Tk.

## Two-process architecture (read `docs/ARCHITECTURE.md` first)

```
PrintWatcher.exe (C# / WinUI 3 / .NET 8)  ──REST + WS on 127.0.0.1──▶  PrintWatcher-backend.exe (Python)
  ShellViewModel ◀ EventStream (WebSocket)                              WatcherCore → EventBus → FastAPI/uvicorn
  ApiClient (HttpClient)                                                (watchdog Observer + PrinterWorker + HistoryStore)
  BackendSupervisor spawns the backend, discovers it via server.json
```

The dividing line is deliberate: **`printwatcher/core.py` (`WatcherCore`, `PrinterWorker`,
`HistoryStore`, `PrintOptions`, `PrintRecord`, `THEMES`, parsers) is UI-agnostic** and is
imported directly by three consumers — the legacy Tk UI, the 25+ `scripts/` helpers, and
the FastAPI server. Changes to printing/watching/history behavior belong in `core.py`, not
in any UI layer, so the two front-ends can't drift.

Key cross-cutting facts a single file won't tell you:

- **The watcher runs in a worker thread**, the server in asyncio. `printwatcher/server/events.py`
  (`EventBus`) bridges them with `loop.call_soon_threadsafe(queue.put_nowait, event)`. Any
  callback fired from `PrinterWorker` into the server must go through that hop.
- **DTOs are mirrored, not generated.** `printwatcher/server/dto.py` (pydantic) and
  `csharp/src/PrintWatcher.Shell/Models/` (C# records) are kept in sync by hand. Edit both.
- **WebSocket frame shapes** (`hello`/`stat`/`log`/`history`/`pending`/`tool`) are documented
  in `docs/ARCHITECTURE.md` and decoded against a discriminated `WsEnvelope` on the C# side.
- **Auth is mandatory, per-launch.** uvicorn binds `127.0.0.1` only; every REST request needs
  `Authorization: Bearer <token>`; the WebSocket must send `{"type":"auth","token":...}` as
  its first frame within 5s or the socket closes with code `4401`. The shell generates the
  token and passes it to the backend it spawns. There is no "same-user" bypass.
- **Backend discovery:** the backend writes `{port, pid, token, version}` to
  `%LOCALAPPDATA%\PrintWatcher\server.json`; the shell polls it. For dev, the env var
  `PRINTWATCHER_DEV_BACKEND="<url>;<token>"` skips spawning + discovery entirely.

The C# test project **cross-compiles the non-WinUI source** (`Models/`, `ViewModels/`,
`Services/EventStream.cs`, `Services/BackendSupervisor.cs`) into a plain `net8.0` project,
so logic tests run on any CI runner without the Windows App SDK.

## CLI dispatch

`printwatcher_app.py` is the unified launcher: no args → desktop UI; `<subcommand>` → the
matching `scripts/*.py` module (each exposes `main(argv) -> int`). The `SUBCOMMANDS` dict
there is the source of truth mapping short names (`pdf-inspect`, `roster`, `backend`, …) to
modules. `backend` launches the FastAPI server. `--list` prints all subcommands.

## Commands

```bash
# Install (editable, with dev + backend extras)
python -m pip install -e ".[dev,backend]"

# Python tests (pytest; asyncio_mode=auto, testpaths=tests/)
pytest -q                          # full suite (what CI runs)
pytest tests/server -v             # just the FastAPI surface
pytest tests/server/test_auth.py::test_name   # single test

# Run the backend by hand (dev)
python -m printwatcher.server --port 8765 --token devtoken
#   flags: --inbox PATH  --sumatra PATH  --no-discovery  --log-level debug

# C# shell against a hand-started backend (Windows + .NET 8 SDK only)
$env:PRINTWATCHER_DEV_BACKEND = "http://127.0.0.1:8765;devtoken"
dotnet run --project csharp/src/PrintWatcher.Shell

# C# tests (cross-platform — no Windows App SDK needed)
dotnet test csharp/PrintWatcher.sln
```

### Production binaries (Windows-only; CI in `.github/workflows/build.yml` is the source of truth)

```powershell
pyinstaller printwatcher-backend.spec --noconfirm   # → dist/PrintWatcher-backend.exe (headless)
pyinstaller printwatcher.spec         --noconfirm   # → dist/PrintWatcher.exe (legacy Tk, renamed -legacy in zip)
pyinstaller printwatcher-cli.spec     --noconfirm   # → dist/PrintWatcher-cli.exe (console dispatcher)

dotnet publish csharp/src/PrintWatcher.Shell/PrintWatcher.Shell.csproj `
  --configuration Release --runtime win-x64 --self-contained true `
  -p:Platform=x64 -p:WindowsAppSDKSelfContained=true --output csharp/publish/shell
```

`-p:Platform=x64` is **mandatory** for the WinUI publish (the csproj declares but doesn't
default to it; `WindowsAppSDK.SelfContained.targets` fails on AnyCPU). Do **not** add
`-p:EnableMsixTooling=false` / `-p:GenerateAppxPackageOnBuild=false` / `-p:PublishSingleFile=true` —
each breaks unpackaged WinUI builds. See `docs/DEV_SETUP.md` for the full rationale.

## Platform constraints

- The C# shell builds/runs on **Windows 10/11 only** (`net8.0-windows10.0.19041.0`).
- The Python backend/FastAPI surface is cross-platform, but the **printing path is
  Windows-only** because it shells out to SumatraPDF (`subprocess` in `core.py`).
- `APP_VERSION` is defined independently in `printwatcher/core.py`, `printwatcher_app.py`,
  and `pyproject.toml` (`version`) — keep all three in sync. `print_watcher_ui.py` imports
  it from `core`, so it doesn't need a separate bump.

## Watched-folder conventions

`core.py` reserves top-level subdirs inside the inbox: `_printed/`, `_skipped/`, `_scheduled/`
(see `RESERVED_TOP_LEVEL`). Printable extensions are `.pdf .png .jpg .jpeg` (`EXTS`). Files are
only printed once stable across `STABLE_CHECKS` polls (avoids printing mid-sync). Per-job
options can be encoded in the filename after a `__` separator (`FILENAME_OPTIONS_SEPARATOR`).
