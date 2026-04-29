"""PrintWatcher environment diagnostic.

Runs every check we kept doing manually while debugging on locked-down
school laptops. Outputs PASS / WARN / FAIL for each check with concrete
remediation hints, and exits 1 if anything FAILs (so it can be wired
into a setup script).

    python scripts/verify_environment.py
    python scripts/verify_environment.py --json   # machine-readable
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


@dataclass
class CheckResult:
    name: str
    status: str               # PASS | WARN | FAIL
    detail: str = ""
    fix: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail, "fix": self.fix}


@dataclass
class Report:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> None:
        self.results.append(result)

    @property
    def has_failures(self) -> bool:
        return any(r.status == FAIL for r in self.results)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

REQUIRED_PYTHON = (3, 10)
REQUIRED_PACKAGES = ("watchdog", "pystray", "PIL")  # PIL = pillow's import name
DEFAULT_SUMATRA_PATH = Path(r"C:\Tools\SumatraPDF\SumatraPDF.exe")
INBOX_NAME = "PrintInbox"


def check_python_version() -> CheckResult:
    actual = sys.version_info[:3]
    if actual >= REQUIRED_PYTHON:
        return CheckResult(
            "Python version",
            PASS,
            f"{actual[0]}.{actual[1]}.{actual[2]} at {sys.executable}",
        )
    return CheckResult(
        "Python version",
        FAIL,
        f"{actual[0]}.{actual[1]} is below required {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}",
        f"Install Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ from python.org and tick 'Add to PATH'.",
    )


def check_ms_store_python() -> CheckResult:
    """MS Store Python's WindowsApps alias breaks Task Scheduler launches."""
    if sys.platform != "win32":
        return CheckResult("MS Store Python alias", PASS, "non-Windows host, not applicable")
    exe = sys.executable.lower()
    if "windowsapps" in exe and "pythonsoftwarefoundation" not in exe:
        return CheckResult(
            "MS Store Python alias",
            WARN,
            f"Python resolves to a WindowsApps alias ({sys.executable}); Task Scheduler can't launch it reliably",
            "Either install Python from python.org (per-user, no admin needed) or use a Startup-folder shortcut instead of Task Scheduler.",
        )
    return CheckResult("MS Store Python alias", PASS, "real interpreter, not the alias")


def check_required_packages() -> CheckResult:
    missing: list[str] = []
    for name in REQUIRED_PACKAGES:
        if importlib.util.find_spec(name) is None:
            missing.append(name)
    if not missing:
        return CheckResult("Required packages", PASS, ", ".join(REQUIRED_PACKAGES) + " installed")
    return CheckResult(
        "Required packages",
        FAIL,
        f"missing: {', '.join(missing)}",
        f"Run: python -m pip install --user {' '.join(missing).replace('PIL', 'pillow')}",
    )


def check_sumatra(path: Path = DEFAULT_SUMATRA_PATH) -> CheckResult:
    if path.exists() and path.is_file():
        return CheckResult("SumatraPDF binary", PASS, f"found at {path}")
    return CheckResult(
        "SumatraPDF binary",
        FAIL,
        f"not found at {path}",
        "Re-run bootstrap.ps1, or download SumatraPDF portable to that path manually.",
    )


def _onedrive_root() -> Path | None:
    for var in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        value = os.environ.get(var)
        if value:
            return Path(value)
    return None


def check_onedrive_env() -> CheckResult:
    root = _onedrive_root()
    if root is None:
        return CheckResult(
            "OneDrive environment",
            FAIL,
            "no OneDrive / OneDriveCommercial / OneDriveConsumer env var set",
            "Sign into OneDrive from the system tray and reopen PowerShell.",
        )
    if not root.exists():
        return CheckResult(
            "OneDrive environment",
            FAIL,
            f"$env:OneDrive points to {root} but the folder does not exist",
            "Wait for OneDrive to finish initial sync, or reset its location.",
        )
    return CheckResult("OneDrive environment", PASS, f"root: {root}")


def check_inbox_folder() -> CheckResult:
    root = _onedrive_root()
    if root is None:
        return CheckResult(
            "PrintInbox folder",
            FAIL,
            "cannot locate OneDrive root, so cannot resolve PrintInbox",
            "Fix the OneDrive environment first.",
        )
    inbox = root / INBOX_NAME
    if not inbox.exists():
        return CheckResult(
            "PrintInbox folder",
            FAIL,
            f"{inbox} is missing",
            "Run bootstrap.ps1 to create it, or `mkdir` it manually.",
        )
    return CheckResult("PrintInbox folder", PASS, f"exists at {inbox}")


def check_default_printer() -> CheckResult:
    if sys.platform != "win32":
        return CheckResult("Default printer", PASS, "non-Windows host, skipped")
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        return CheckResult(
            "Default printer", WARN,
            "PowerShell not on PATH; cannot query default printer",
        )
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Printer | Where-Object Default).Name"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult("Default printer", WARN, f"PowerShell query failed: {exc}")

    name = result.stdout.strip()
    if not name:
        return CheckResult(
            "Default printer", FAIL,
            "no default printer is set",
            "Settings -> Bluetooth & devices -> Printers & scanners -> select a printer -> Set as default. Also turn off 'Let Windows manage my default printer'.",
        )
    return CheckResult("Default printer", PASS, name)


def check_printix() -> CheckResult:
    """Soft signal — Printix client running suggests it can spool jobs."""
    if sys.platform != "win32":
        return CheckResult("Printix client", PASS, "non-Windows host, skipped")
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        return CheckResult("Printix client", WARN, "PowerShell unavailable; cannot detect")
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-Command",
             "Get-Process -Name 'PrintixClient','PrintixService' -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Name"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult("Printix client", WARN, f"detection failed: {exc}")
    name = result.stdout.strip()
    if name:
        return CheckResult("Printix client", PASS, f"{name} process is running")
    return CheckResult(
        "Printix client", WARN,
        "no Printix process detected (this is fine if you don't use Printix)",
        "If you do use Printix: open the tray icon and sign in. Held jobs need release at the printer.",
    )


def check_watcher_paths_patched(repo_root: Path) -> CheckResult:
    """Make sure bootstrap.ps1 has rewritten the placeholder paths."""
    target = repo_root / "print_watcher_tray.py"
    if not target.exists():
        return CheckResult(
            "Watcher paths patched",
            WARN,
            "print_watcher_tray.py not found next to verify script",
            "Run from inside the PrintWatcher repo folder.",
        )
    text = target.read_text(encoding="utf-8", errors="ignore")
    if "YOUR_USERNAME" in text:
        return CheckResult(
            "Watcher paths patched",
            FAIL,
            "print_watcher_tray.py still contains YOUR_USERNAME placeholder",
            "Run .\\bootstrap.ps1 to patch the paths for this machine.",
        )
    inbox_match = re.search(r'WATCH_DIR\s*=\s*Path\(r"([^"]+)"\)', text)
    sumatra_match = re.search(r'SUMATRA\s*=\s*Path\(r"([^"]+)"\)', text)
    detail_lines = []
    if inbox_match:
        detail_lines.append(f"inbox = {inbox_match.group(1)}")
    if sumatra_match:
        detail_lines.append(f"sumatra = {sumatra_match.group(1)}")
    return CheckResult("Watcher paths patched", PASS, "; ".join(detail_lines) or "ok")


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _color_for(status: str) -> str:
    if not sys.stdout.isatty():
        return ""
    return {PASS: "\033[32m", WARN: "\033[33m", FAIL: "\033[31m"}.get(status, "")


_RESET = "\033[0m"


def render_text(report: Report) -> str:
    lines: list[str] = []
    lines.append("PrintWatcher environment check")
    lines.append("=" * 60)
    width = max(len(r.name) for r in report.results) + 2
    for r in report.results:
        color = _color_for(r.status)
        reset = _RESET if color else ""
        lines.append(f"  {r.name.ljust(width)} {color}{r.status:<4}{reset}  {r.detail}")
        if r.fix and r.status != PASS:
            lines.append(f"  {' ' * width}       fix: {r.fix}")
    lines.append("")
    counts = {s: sum(1 for r in report.results if r.status == s) for s in (PASS, WARN, FAIL)}
    lines.append(f"  {counts[PASS]} pass   {counts[WARN]} warn   {counts[FAIL]} fail")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_all(repo_root: Path) -> Report:
    report = Report()
    checks: Iterable = (
        check_python_version,
        check_ms_store_python,
        check_required_packages,
        check_sumatra,
        check_onedrive_env,
        check_inbox_folder,
        check_default_printer,
        check_printix,
        lambda: check_watcher_paths_patched(repo_root),
    )
    for check in checks:
        try:
            report.add(check())
        except Exception as exc:  # pragma: no cover - last-resort guard
            report.add(CheckResult(
                getattr(check, "__name__", "check"),
                FAIL,
                f"raised {type(exc).__name__}: {exc}",
                "File a bug — verify_environment.py should never raise.",
            ))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PrintWatcher environment diagnostic")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    report = run_all(repo_root)

    if args.json:
        print(json.dumps([r.to_dict() for r in report.results], indent=2))
    else:
        print(render_text(report))

    return 1 if report.has_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
