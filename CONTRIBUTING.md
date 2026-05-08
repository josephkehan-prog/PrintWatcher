# Contributing to PrintWatcher

PrintWatcher is two cooperating processes on a single Windows desktop —
a Python file-watcher / FastAPI backend and a WinUI 3 shell. Most
contributors only need the Python half running; the WinUI shell builds
under Windows + .NET 8 SDK.

## Quick setup (Python side)

```bash
git clone https://github.com/josephkehan-prog/PrintWatcher
cd PrintWatcher
pip install -e ".[dev,backend]"
```

## Run the test suite

```bash
pytest                              # all tests
pytest --cov=printwatcher           # with coverage (CI gate is 65%)
pytest tests/test_dto_parity.py     # one file
```

Tests stub `watchdog` and `tkinter` so they run on headless Linux/macOS
runners — see `tests/conftest.py` and `tests/server/conftest.py`.

## Lint and security

```bash
ruff check printwatcher/ print_watcher_tray.py    # style / bugs
bandit -r printwatcher/ -ll                       # security (medium+)
```

CI runs both with the same flags. PR review expects a clean run.

## WinUI shell

The shell lives in `csharp/src/PrintWatcher.Shell/`. Build it on
Windows:

```pwsh
cd csharp
dotnet restore PrintWatcher.sln
dotnet build PrintWatcher.sln --configuration Release
dotnet test src/PrintWatcher.Shell.Tests/
```

CI publishes a self-contained win-x64 build on every push (see
`.github/workflows/build.yml`).

## Architecture quick map

- `printwatcher/core.py` — `WatcherCore`, `PrinterWorker`,
  `HistoryStore`, watchdog handler, polling rescanner. The Tk UI and
  the FastAPI backend both construct one of these.
- `printwatcher/server/` — FastAPI app, routes, DTOs, websocket.
- `print_watcher_tray.py` — minimal alternative entrypoint (no UI).
- `print_watcher_ui.py` — **deprecated**, removed in v0.5. Do not
  refactor.
- `csharp/src/PrintWatcher.Shell/` — WinUI 3 shell, the canonical UI
  from v0.4 onward.

See `docs/ARCHITECTURE.md` for the full picture.

## Pull request flow

1. Branch off `main`. Naming: `claude/<short-topic>` or
   `fix/<topic>` / `feat/<topic>` / `refactor/<topic>`.
2. Keep PRs focused — one bug fix, one feature, one refactor. Don't
   combine.
3. Add tests for new behavior and for any bug you fix. New tests for
   bug fixes should fail on `main` and pass on your branch.
4. Run `pytest`, `ruff check`, `bandit -ll` before pushing.
5. CI must be green before review. The `Test + Build Windows binaries`
   job is the gate.
6. Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`,
   `test:`, `chore:`, `perf:`, `ci:`.
7. Reference the issue/PR in the description, not the title.

## DTO parity

The Python Pydantic DTOs in `printwatcher/server/dto.py` and the C#
records in `csharp/src/PrintWatcher.Shell/Models/*.cs` are kept in sync
by `tests/test_dto_parity.py`. If you rename a field, update both
sides; the test will catch one-sided changes.

## Reporting bugs and security issues

Bugs: open an issue at
<https://github.com/josephkehan-prog/PrintWatcher/issues>.

Security: see [SECURITY.md](SECURITY.md). Don't open a public issue for
suspected vulnerabilities.
