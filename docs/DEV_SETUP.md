# Dev setup

You need **two terminals** for the v0.4 architecture: one runs the Python
backend, the other runs the C# / WinUI 3 shell. The shell can also be
pointed at a backend running anywhere with the `PRINTWATCHER_DEV_BACKEND`
env var, which skips the bundled `Process.Start` path entirely.

> **OS note.** The shell only builds and runs on Windows 10/11
> (`net8.0-windows10.0.19041.0`). The Python backend is cross-platform
> (the FastAPI surface runs anywhere), but the printing path is Windows-
> only because it shells out to SumatraPDF.

## Prerequisites

- Windows 10 or 11
- Python 3.10+ on PATH
- .NET 8 SDK (`winget install Microsoft.DotNet.SDK.8`)
- A clone of this repo, opened in PowerShell

The C# project pins .NET 8.0.x via `csharp/global.json` — if you only have
.NET 9 installed, either install 8 or update `global.json` to match.

## Install Python deps

```powershell
python -m pip install -e ".[dev,backend]"
```

`dev` pulls in pytest, httpx, pyinstaller, and the optional PDF deps used
by the helper scripts. `backend` pulls in fastapi + uvicorn + pydantic +
python-multipart.

## Terminal 1 — Python backend

```powershell
python -m printwatcher.server --port 8765 --token devtoken
```

You should see:

```
INFO:     Started server process [...]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8765 ...
```

Optional flags:

| Flag | Default | Purpose |
|---|---|---|
| `--port N` | `0` (ephemeral) | bind a fixed port; useful for the shell env var |
| `--token <hex>` | random | bearer token; set explicitly so the shell can match |
| `--inbox <path>` | discovered | watch directory override |
| `--sumatra <path>` | discovered | path to `SumatraPDF.exe` |
| `--no-discovery` | off | skip writing `server.json` (testing only) |
| `--log-level info\|debug\|...` | `info` | uvicorn log verbosity |

### Discovery file

When `--no-discovery` is **not** passed, the backend writes
`{port, pid, token, version}` to:

```
%LOCALAPPDATA%\PrintWatcher\server.json
```

The C# shell's production launch path reads this file. You only need to
care about it if you're debugging the supervisor — for everyday dev,
`PRINTWATCHER_DEV_BACKEND` skips it.

### Port already in use

If you re-launch the backend and see:

```
ERROR: [Errno 10048] error while attempting to bind on address
('127.0.0.1', 8765): only one usage of each socket address …
```

an earlier instance is still holding the port. Find and stop it:

```powershell
Get-NetTCPConnection -LocalPort 8765 |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

Or just pick a different port for this run (`--port 8766`) and update the
shell env var to match.

## Terminal 2 — C# / WinUI shell

```powershell
$env:PRINTWATCHER_DEV_BACKEND = "http://127.0.0.1:8765;devtoken"
cd csharp\src\PrintWatcher.Shell
dotnet run
```

The env var has the form `<base-url>;<token>`. When set,
`BackendSupervisor` skips spawning a backend process and connects to the
URL directly using the supplied token — fast inner loop, single-process
debugging.

If you want the shell to fall back to its production behaviour (spawn its
own backend), unset the env var:

```powershell
Remove-Item Env:\PRINTWATCHER_DEV_BACKEND
```

…and put a built `PrintWatcher-backend.exe` next to the shell binary
(see "Production build" below).

## Tests

```powershell
# Python — pytest from the repo root
pytest tests/server -v

# C# — xUnit (cross-compiles non-WinUI source files into a plain net8.0 project,
# so this works on any runner, no Windows App SDK required)
dotnet test csharp\PrintWatcher.sln
```

Both suites also run on every push in the CI workflow under
`.github/workflows/build.yml`.

## Production build

The CI job in `.github/workflows/build.yml` is the source of truth, but
locally:

```powershell
# 1. Python backend binary (no console)
pyinstaller printwatcher-backend.spec --noconfirm
# → dist\PrintWatcher-backend.exe

# 2. Legacy Tk binary (still shipped through v0.5)
pyinstaller printwatcher.spec --noconfirm
# → dist\PrintWatcher.exe (will be renamed PrintWatcher-legacy.exe in the release zip)

# 3. CLI binary
pyinstaller printwatcher-cli.spec --noconfirm
# → dist\PrintWatcher-cli.exe

# 4. C# shell (self-contained single-file)
dotnet publish csharp\src\PrintWatcher.Shell\PrintWatcher.Shell.csproj `
  -c Release -r win-x64 --self-contained true `
  -p:PublishSingleFile=true `
  -p:IncludeNativeLibrariesForSelfExtract=true `
  -o publish\shell
# → publish\shell\PrintWatcher.exe (~85 MB; .NET 8 + Windows App SDK bundled)
```

Drop `PrintWatcher.exe` and `PrintWatcher-backend.exe` into the same
folder; the shell launches the backend by relative path.

## Common issues

**`dotnet --list-sdks` shows only 9.0** — install .NET 8 (`winget install
Microsoft.DotNet.SDK.8`) or relax `csharp/global.json` to allow 9.

**Shell says "discovery file not found"** — the backend never wrote
`server.json`. Either it crashed at startup (check Terminal 1) or you
passed `--no-discovery`. For dev, just set `PRINTWATCHER_DEV_BACKEND` and
skip the discovery path entirely.

**Shell connects but receives no events** — the WebSocket auth frame
probably failed. Confirm the token in your env var matches the `--token`
you passed to the backend. Mismatched tokens close the socket with
code `4401`.

**Stale outer-folder confusion** — if you cloned into a folder that
already had old PrintWatcher files, the freshly-cloned repo lands in a
**nested** subfolder. `ls` should show `csharp\`, `printwatcher\`,
`print_watcher_ui.py` — if it doesn't, `cd` one level deeper.
