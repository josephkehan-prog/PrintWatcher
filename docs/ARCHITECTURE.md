# Architecture

PrintWatcher v0.4 ships as **two cooperating processes** on a single Windows
machine: a native C# / WinUI 3 shell (`PrintWatcher.exe`) and a headless
Python backend (`PrintWatcher-backend.exe`). The shell is the user-facing
window and tray icon; the backend owns the file watcher, the printer worker,
and the on-disk history. They speak REST + WebSocket on `127.0.0.1` only.

```
┌──────────────────────────────────────────────────────────────────────┐
│  PrintWatcher.exe   (C# / WinUI 3 / .NET 8 self-contained)           │
│                                                                      │
│   MainWindow ◀── ShellViewModel ◀── EventStream (ClientWebSocket)    │
│                                          ▲                           │
│                       ApiClient (HttpClient)  ─── REST ──┐           │
│                                                          │           │
│   BackendSupervisor — Process.Start("PrintWatcher-       │           │
│                          backend.exe"), reads server.json│           │
└──────────────────────────────────────────┬───────────────┴───────────┘
                                           │ TCP loopback (REST + WS)
┌──────────────────────────────────────────▼───────────────────────────┐
│  PrintWatcher-backend.exe   (Python, PyInstaller --noconsole)        │
│                                                                      │
│   WatcherCore ──▶ EventBus ──▶ FastAPI app (uvicorn on 127.0.0.1)    │
│   (Observer +     (asyncio.Queue                                     │
│    PrinterWorker  fan-out)                                           │
│    + HistoryStore)                                                   │
└──────────────────────────────────────────────────────────────────────┘
```

## Why two processes?

The legacy desktop UI (`print_watcher_ui.py`, ~2,200 lines of Tk + customtkinter)
carries the visible cost of the Tk widget set: no per-widget alpha, no GPU
animation, brittle theming, accessibility limited to font scaling. The
**watcher** itself — `watchdog.Observer`, `PrinterWorker`, `HistoryStore`,
the 25+ scripts under `scripts/` — has always been UI-agnostic, and is the
only part that needs to keep running when the window is hidden.

Splitting along that boundary lets us:

- Replace only the UI layer with a native Win11 shell (Mica backdrops, real
  animations, `AutomationProperties` accessibility, `NavigationView` chrome)
  without touching the watcher.
- Keep the entire `scripts/` ecosystem untouched — they still import from
  `printwatcher.core` directly, no REST round-trip.
- Run the watcher even when the shell is closed (tray-only mode), and start
  the shell against a backend that's already been printing for hours.

## Repository layout

The Python side stays a regular package; the C# side is a sibling solution.

```
/PrintWatcher
  print_watcher_ui.py             # legacy Tk UI — ships through v0.5, deleted in v0.6
  printwatcher_app.py             # CLI dispatcher (subcommand `backend` launches the server)

  printwatcher/                   # importable from Tk UI, scripts/, AND the server
    __init__.py                   # re-exports all public names
    core.py                       # WatcherCore, PrinterWorker, HistoryStore,
                                  #   PrintOptions, PrintRecord, THEMES, parsers
    server/                       # FastAPI surface
      __main__.py                 # `python -m printwatcher.server` entry
      app.py                      # FastAPI app factory + middleware
      auth.py                     # bearer-token dependency (HMAC-safe compare)
      events.py                   # EventBus (asyncio.Queue + thread-safe entry)
      websocket.py                # /ws fan-out, auth-as-first-frame
      tools.py                    # tool runner with stdout/logging capture
      dto.py                      # pydantic DTOs (mirrored on the C# side)
      state.py                    # state snapshot builder
      routes/                     # one module per endpoint group

  csharp/                         # .NET 8 / WinUI 3 solution
    PrintWatcher.sln
    Directory.Build.props
    global.json
    src/
      PrintWatcher.Shell/         # WinUI 3 app, output: PrintWatcher.exe
        App.xaml(.cs)             # entry, single-instance, backend supervision
        MainWindow.xaml(.cs)      # NavigationView host
        Pages/DashboardPage.xaml  # status pip + 4 stat tiles + activity log
        Services/ApiClient.cs     # typed HttpClient wrapper
        Services/EventStream.cs   # ClientWebSocket + reconnect/backoff
        Services/BackendSupervisor.cs  # Process.Start, server.json discovery
        Services/ThemePalette.cs  # ThemeRegistry — port of the Python THEMES dict
        ViewModels/               # DashboardViewModel, ShellViewModel, …
        Models/                   # PrintRecord, PrintOptions, WsEnvelope, …
      PrintWatcher.Shell.Tests/   # xUnit — cross-compiles non-WinUI source files

  printwatcher.spec               # legacy Tk binary (unchanged through v0.5)
  printwatcher-cli.spec           # CLI binary (unchanged)
  printwatcher-backend.spec       # NEW — headless Python backend binary

  tests/server/                   # pytest suite for the FastAPI surface
```

The C# tests cross-compile most non-WinUI source files (`Models/`,
`ViewModels/`, `Services/EventStream.cs`, `Services/BackendSupervisor.cs`)
into a plain `net8.0` test project, so they run on any CI runner — no
Windows App SDK required to validate logic.

## Data flow

### Boot

1. User double-clicks `PrintWatcher.exe`.
2. `App.xaml.cs` checks for the single-instance mutex (a second launch
   redirects activation to the existing instance and exits).
3. `BackendSupervisor.StartAsync` either:
   - reads `PRINTWATCHER_DEV_BACKEND` (an env var of the form `url;token`)
     and connects to a backend the developer started by hand, **or**
   - generates a random 32-byte hex token, spawns
     `PrintWatcher-backend.exe --port 0 --token <hex>`, and polls
     `%LOCALAPPDATA%/PrintWatcher/server.json` for up to 10 seconds waiting
     for the backend to write `{port, pid, token, version}`.
4. The shell calls `GET /api/state` to seed the dashboard, then opens
   `ws://127.0.0.1:<port>/ws` for live updates.
5. `MainWindow` is shown.

### Live updates

Inside the backend, `PrinterWorker` is still a `threading.Thread`. When it
prints a file, it calls back into `EventBus.publish({...})`. `EventBus` uses
`loop.call_soon_threadsafe(queue.put_nowait, event)` to hand the event from
the worker thread to the asyncio event loop, where `/ws` subscribers receive
it. The shell's `EventStream` parses each frame against a discriminated
`WsEnvelope` (System.Text.Json source-generated for AOT-friendly perf) and
dispatches via `DispatcherQueue.TryEnqueue` so ViewModels can mutate
`ObservableCollection`s on the UI thread.

Frame shapes (one JSON message per frame):

```jsonc
{"type": "hello",   "port": 53872, "version": "0.4.0"}
{"type": "stat",    "key": "printed", "delta": 1, "value": 42}
{"type": "log",     "ts": "...", "level": "info", "line": "queued: foo.pdf"}
{"type": "history", "record": {/* full PrintRecord */}}
{"type": "pending", "items": [{"path": "...", "name": "foo.pdf"}]}
{"type": "tool",    "run_id": "abc", "stream": "stdout", "line": "..."}
{"type": "tool",    "run_id": "abc", "stream": "end", "rc": 0}
```

### Shutdown

The window's close button hides to tray; the watcher keeps running.
**Quit** (from the tray menu) calls `POST /api/shutdown`, waits 2 s, then
`Process.Kill(entireProcessTree: true)` if the backend is still alive. The
discovery file is deleted on clean exit.

## Security model

Loopback-only is enforced two ways: uvicorn binds `127.0.0.1` (never
`0.0.0.0`), and every HTTP request must carry
`Authorization: Bearer <token>`. The WebSocket handshake works the same
way — the client must send `{"type":"auth","token":"..."}` as its first
frame within 5 seconds, or the socket is closed with code `4401`.

The token is generated **per launch** by the C# shell and only the shell
that spawned the backend knows it. There is no auth bypass for "the same
user" — the token gate is strict because the backend would otherwise be
indistinguishable from a print server to anything else running on the box.

`server.json` contains the token, but it lives in `%LOCALAPPDATA%`
(per-user) and is deleted on clean shutdown.

## REST surface

| Method | Path | Purpose |
|---|---|---|
| GET    | `/api/state` | boot snapshot — stats, hold_mode, options, theme, pending, printers |
| POST   | `/api/pause` | `{paused: bool}` |
| GET/PUT| `/api/options` | `PrintOptions` (printer/copies/sides/color) |
| GET    | `/api/printers` | `{default, list}` |
| POST   | `/api/printers/refresh` | re-runs PowerShell `Get-Printer` |
| GET    | `/api/history?limit=200&q=&regex=&from=&to=` | filtered records |
| DELETE | `/api/history` | clear store |
| GET    | `/api/pending` | hold queue |
| POST   | `/api/pending/print` | release all held |
| POST   | `/api/pending/skip` | move all held to `_skipped/` |
| GET/PUT| `/api/preferences` | theme + a11y prefs |
| GET    | `/api/themes` | the `THEMES` dict (read-only mirror) |
| POST   | `/api/tools/run` | `{module, args, label}` → `{run_id}` |
| POST   | `/api/inbox/drop` | multipart upload → write into inbox |
| POST   | `/api/shutdown` | clean exit |

Full DTO definitions live in `printwatcher/server/dto.py` (Python) and
`csharp/src/PrintWatcher.Shell/Models/` (C#) — they are mirrored, not
generated.

## Rollout plan

| Version | Binaries shipped | Default double-click |
|---|---|---|
| **v0.4** | `PrintWatcher.exe` (C# shell) + `PrintWatcher-backend.exe` + `PrintWatcher-cli.exe` + `PrintWatcher-legacy.exe` (Tk) | C# shell |
| **v0.5** | Same four. Tk emits a deprecation log line on startup. | C# shell |
| **v0.6** | Three binaries — Tk deleted, `customtkinter` dependency dropped, `printwatcher.spec` removed. | C# shell |

Both UI flavours import the same `WatcherCore` during the runway, so
behaviour cannot drift between them. The C# shell never sees Tk; Tk never
sees the backend's REST surface — they are independent skins over the same
core.

## See also

- [`docs/DEV_SETUP.md`](DEV_SETUP.md) — running both processes locally
- `printwatcher/core.py` — `WatcherCore` facade and pub/sub callbacks
- `printwatcher/server/app.py` — FastAPI app factory
- `csharp/src/PrintWatcher.Shell/App.xaml.cs` — shell startup wiring
