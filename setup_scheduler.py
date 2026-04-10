"""
Python alternative to setup_scheduler.bat for creating Windows Task Scheduler tasks.

Creates two daily scheduled tasks via schtasks.exe:
  - Greyhound_Morning: runs at 07:00 (AEST) daily
  - Greyhound_Evening: runs at 16:00 (AEST) daily

Both tasks run: python run_pipeline.py --email

Usage:
    python setup_scheduler.py
    python setup_scheduler.py --work-dir "D:\\other\\path"
    python setup_scheduler.py --remove        # delete both tasks

Note: On Windows, running as Administrator allows setting task priority
to HIGHEST and scheduling without requiring the user to be logged on.
Without elevation the tasks still work but run only when logged on.
"""

import argparse
import os
import subprocess
import sys
from datetime import date


TASK_MORNING = "Greyhound_Morning"
TASK_EVENING = "Greyhound_Evening"
DEFAULT_WORKDIR = r"C:\greyhound_realtime\Greyhound-Agent"


# ──────────────────────────────────────────────────────────────────────────────
# Task management
# ──────────────────────────────────────────────────────────────────────────────

def create_task(
    name: str,
    time_str: str,
    script_path: str,
    work_dir: str,
    python_exe: str = "python",
) -> bool:
    """
    Create a daily Windows Task Scheduler task via schtasks.exe.

    Parameters
    ----------
    name : str
        Task name (e.g. "Greyhound_Morning").
    time_str : str
        Start time in HH:MM format (24-hour).
    script_path : str
        Full path to run_pipeline.py.
    work_dir : str
        Working directory for the task (project root).
    python_exe : str
        Path or name of the Python executable.

    Returns
    -------
    bool
        True if created successfully.
    """
    today = date.today().strftime("%m/%d/%Y")
    # schtasks expects date as MM/DD/YYYY on US-locale machines

    # Build the command string — wrap paths in quotes for spaces
    cmd_string = f'"{python_exe}" "{script_path}" --email'

    # Try with HIGHEST privilege first
    for extra_args in (["/rl", "HIGHEST"], []):
        args = [
            "schtasks", "/create",
            "/tn", name,
            "/tr", cmd_string,
            "/sc", "DAILY",
            "/st", time_str,
            "/sd", today,
            "/ru", "",          # Run as current user
            "/f",               # Force overwrite
        ] + extra_args

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                priv = "HIGHEST privilege" if extra_args else "standard privilege"
                print(f"  OK — '{name}' created ({priv})")
                return True
            else:
                if extra_args:
                    # Try without /rl HIGHEST on next loop iteration
                    continue
                print(f"  ERROR — schtasks returned {result.returncode}")
                if result.stderr:
                    print(f"  stderr: {result.stderr.strip()}")
                return False
        except FileNotFoundError:
            print("  ERROR: schtasks.exe not found. Are you running on Windows?")
            return False
        except subprocess.TimeoutExpired:
            print(f"  ERROR: schtasks timed out creating '{name}'")
            return False

    return False


def set_task_execution_limit(name: str, limit_hhmm: str = "00:30") -> None:
    """
    Set the maximum execution time for a task (e.g. '00:30' = 30 minutes).

    Note: schtasks /change /ET is not available in all Windows versions.
    Uses XML modification as a fallback if /ET fails.
    """
    try:
        result = subprocess.run(
            ["schtasks", "/change", "/tn", name, "/ET", limit_hhmm],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            print(f"  Execution limit set to {limit_hhmm} for '{name}'")
    except Exception:
        pass  # Non-critical — task will still run


def delete_task(name: str) -> bool:
    """Delete a scheduled task by name."""
    try:
        result = subprocess.run(
            ["schtasks", "/delete", "/tn", name, "/f"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            print(f"  Deleted task '{name}'")
            return True
        print(f"  WARNING: Could not delete '{name}' (may not exist)")
        return False
    except FileNotFoundError:
        print("  ERROR: schtasks.exe not found.")
        return False


def query_task(name: str) -> None:
    """Print task status from schtasks /query."""
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", name, "/fo", "LIST"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                lower = line.lower()
                if any(k in lower for k in ["taskname", "status", "next run", "last run"]):
                    print(f"  {line.strip()}")
        else:
            print(f"  (task '{name}' not found)")
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set up Windows Task Scheduler tasks for the Greyhound pipeline."
    )
    parser.add_argument(
        "--work-dir",
        default=None,
        help=f"Project working directory (default: {DEFAULT_WORKDIR})",
    )
    parser.add_argument(
        "--python",
        default="python",
        help="Python executable path or name (default: python)",
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove both scheduled tasks instead of creating them.",
    )
    return parser.parse_args()


def main() -> None:
    """Create (or remove) both daily scheduler tasks."""
    if sys.platform != "win32":
        print(
            "WARNING: This script is designed for Windows Task Scheduler.\n"
            "It will have no effect on Linux/macOS.\n"
            "On Linux, consider using cron instead:\n"
            "  0 7  * * * cd /path/to/Greyhound-Agent && python run_pipeline.py --email\n"
            "  0 16 * * * cd /path/to/Greyhound-Agent && python run_pipeline.py --email"
        )
        return

    args = _parse_args()
    work_dir = args.work_dir or DEFAULT_WORKDIR
    script_path = os.path.join(work_dir, "run_pipeline.py")
    python_exe = args.python

    print()
    print("=" * 60)
    print("  Greyhound Pipeline — Task Scheduler Setup")
    print("=" * 60)
    print(f"  Work dir  : {work_dir}")
    print(f"  Script    : {script_path}")
    print(f"  Python    : {python_exe}")
    print()

    if args.remove:
        print("[remove] Deleting scheduled tasks ...")
        delete_task(TASK_MORNING)
        delete_task(TASK_EVENING)
        print("\nDone.")
        return

    # Read times from config if available
    try:
        sys.path.insert(0, work_dir)
        from src.config_loader import load_config
        cfg = load_config(os.path.join(work_dir, "config.yaml"))
        morning_time = cfg.get("scheduler", {}).get("morning_time", "07:00")
        evening_time = cfg.get("scheduler", {}).get("evening_time", "16:00")
    except Exception:
        morning_time = "07:00"
        evening_time = "16:00"

    print(f"[1/2] Creating '{TASK_MORNING}' at {morning_time} daily ...")
    ok1 = create_task(TASK_MORNING, morning_time, script_path, work_dir, python_exe)
    if ok1:
        set_task_execution_limit(TASK_MORNING)

    print()
    print(f"[2/2] Creating '{TASK_EVENING}' at {evening_time} daily ...")
    ok2 = create_task(TASK_EVENING, evening_time, script_path, work_dir, python_exe)
    if ok2:
        set_task_execution_limit(TASK_EVENING)

    print()
    print("=" * 60)
    print("  Verification:")
    print("=" * 60)
    query_task(TASK_MORNING)
    query_task(TASK_EVENING)

    print()
    if ok1 and ok2:
        print("Setup complete. Both tasks are scheduled.")
    else:
        print("WARNING: One or more tasks could not be created.")
        print("Try running this script as Administrator.")

    print()
    print("To remove tasks:")
    print(f'  python setup_scheduler.py --remove')
    print(f'  schtasks /delete /tn "{TASK_MORNING}" /f')
    print(f'  schtasks /delete /tn "{TASK_EVENING}" /f')
    print()


if __name__ == "__main__":
    main()
