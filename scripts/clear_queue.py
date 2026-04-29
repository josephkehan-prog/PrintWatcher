"""List or clear stuck Windows print-queue jobs.

Wraps PowerShell's Get-PrintJob / Remove-PrintJob so you don't need to
open Settings > Printers > queue every time something jams.

Usage:
    python scripts/clear_queue.py                   # list all jobs
    python scripts/clear_queue.py --printer "Printix Anywhere"
    python scripts/clear_queue.py --all --confirm   # cancel everything

Without --confirm the script always operates in dry-run mode, so you
can preview what would be removed before committing.

Stdlib only. Windows-only (uses powershell).
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime

log = logging.getLogger("printwatcher.clear_queue")


def _run_powershell(command: str) -> tuple[int, str, str]:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        return 127, "", "PowerShell not on PATH"
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    return result.returncode, result.stdout, result.stderr


def list_jobs(printer: str | None) -> list[dict]:
    selector = f"Get-Printer -Name '{printer}'" if printer else "Get-Printer"
    command = (
        f"{selector} | ForEach-Object {{ Get-PrintJob -PrinterName $_.Name }} "
        "| Select-Object Id, JobStatus, DocumentName, UserName, "
        "SubmittedTime, PagesPrinted, TotalPages, PrinterName "
        "| ConvertTo-Json -Depth 2"
    )
    rc, out, err = _run_powershell(command)
    if rc != 0:
        log.error("PowerShell exit %d: %s", rc, err.strip())
        return []
    out = out.strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        log.error("could not parse PowerShell output: %s", exc)
        return []
    if isinstance(data, dict):
        return [data]
    return data


def remove_job(printer: str, job_id: int) -> bool:
    rc, _, err = _run_powershell(
        f"Remove-PrintJob -PrinterName '{printer}' -ID {job_id}"
    )
    if rc != 0:
        log.warning("could not remove job %s on %s: %s", job_id, printer, err.strip())
        return False
    return True


def render_jobs(jobs: list[dict]) -> str:
    if not jobs:
        return "(no jobs in queue)"
    lines = []
    width_doc = max(len(j.get("DocumentName") or "") for j in jobs)
    width_doc = min(60, max(20, width_doc))
    header = f"  {'ID':>5} {'PRINTER':<28} {'STATUS':<14} {'DOC':<{width_doc}} {'USER':<14} SUBMITTED"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for job in jobs:
        submitted = job.get("SubmittedTime") or ""
        if isinstance(submitted, str) and "/Date(" in submitted:
            try:
                ms = int(submitted.split("(")[1].split(")")[0].split("+")[0].rstrip("-"))
                submitted = datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")
            except (ValueError, IndexError):
                pass
        lines.append(
            f"  {job.get('Id', ''):>5} "
            f"{(job.get('PrinterName') or '')[:28]:<28} "
            f"{(job.get('JobStatus') or '')[:14]:<14} "
            f"{(job.get('DocumentName') or '')[:width_doc]:<{width_doc}} "
            f"{(job.get('UserName') or '')[:14]:<14} "
            f"{submitted}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--printer", help="restrict to one printer")
    parser.add_argument("--id", type=int, help="remove only this job ID")
    parser.add_argument("--all", action="store_true", help="remove every job in scope")
    parser.add_argument("--confirm", action="store_true",
                        help="actually delete (otherwise dry-run preview only)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if sys.platform != "win32":
        log.error("clear_queue.py is Windows-only")
        return 2

    jobs = list_jobs(args.printer)
    print(render_jobs(jobs))

    if not jobs:
        return 0

    if not args.id and not args.all:
        return 0  # listing only

    targets = jobs
    if args.id:
        targets = [j for j in jobs if j.get("Id") == args.id]
        if not targets:
            log.error("no job with id %d", args.id)
            return 1

    if not args.confirm:
        log.info("\nDry-run — would remove %d job(s). Re-run with --confirm.",
                 len(targets))
        return 0

    removed = 0
    for job in targets:
        if remove_job(job["PrinterName"], job["Id"]):
            removed += 1
            log.info("removed job %s on %s", job["Id"], job["PrinterName"])
    log.info("\n%d/%d job(s) removed", removed, len(targets))
    return 0 if removed == len(targets) else 1


if __name__ == "__main__":
    raise SystemExit(main())
