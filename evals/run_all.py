"""
A tiny, dependency-free eval runner for agi-lab.

Discovers Python files under the same directory (evals/) and executes
each with the same Python interpreter. Exit code 0 means success.

Usage: python evals/run_all.py [--timeout SECONDS] [--json-output FILE]

Each eval runs as its own process with stdin closed and a wall-clock
limit (default 60 seconds, --timeout 0 disables the limit), so a script
that loops or waits on input cannot hang the whole run.

Exit codes:
  0  every eval passed
  1  at least one eval failed or timed out
  2  every eval passed but the --json-output summary could not be written
"""
import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))

DEFAULT_TIMEOUT = 60


def discover_eval_files(root_dir):
    files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Skip __pycache__ directories
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            # Exclude this runner file itself
            if os.path.abspath(full) == os.path.abspath(__file__):
                continue
            # Exclude __init__.py files by default (treat them as package helpers)
            if fn == "__init__.py":
                continue
            files.append(full)
    files.sort()
    return files


def _as_text(value):
    """Partial output from TimeoutExpired may be str, bytes or None."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def run_file(path, timeout=DEFAULT_TIMEOUT):
    """Run one eval script. `timeout` in seconds; 0 or None means no limit."""
    limit = timeout if timeout else None
    rel = os.path.relpath(path, start=SCRIPT_DIR)
    try:
        proc = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=limit,
        )
        return {
            "path": rel,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "passed": proc.returncode == 0,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as e:
        stderr = _as_text(e.stderr)
        note = f"runner: timed out after {limit} seconds (raise or disable with --timeout)"
        return {
            "path": rel,
            "returncode": None,
            "stdout": _as_text(e.stdout),
            "stderr": (stderr + "\n" if stderr and not stderr.endswith("\n") else stderr) + note,
            "passed": False,
            "timed_out": True,
        }
    except Exception as e:
        return {
            "path": rel,
            "returncode": None,
            "stdout": "",
            "stderr": f"runner error: {e}",
            "passed": False,
            "timed_out": False,
        }


def print_report(results):
    all_passed = True
    for r in results:
        if r.get("timed_out"):
            status = "TIMEOUT"
        elif r.get("passed"):
            status = "PASS"
        else:
            status = "FAIL"
        code = r.get("returncode")
        print(f"[{status}] {r.get('path')} (exit={code})")
        if r.get("stdout"):
            out = r["stdout"].rstrip()
            if out:
                print("  stdout:")
                for line in out.splitlines():
                    print(f"    {line}")
        if r.get("stderr"):
            err = r["stderr"].rstrip()
            if err:
                print("  stderr:")
                for line in err.splitlines():
                    print(f"    {line}")
        print("")
        if not r.get("passed"):
            all_passed = False

    passed = sum(1 for r in results if r.get("passed"))
    timed_out = sum(1 for r in results if r.get("timed_out"))
    failed = len(results) - passed - timed_out
    print(f"{passed} passed, {failed} failed, {timed_out} timed out")
    return all_passed


def parse_timeout(value):
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("--timeout takes a whole number of seconds")
    if seconds < 0:
        raise argparse.ArgumentTypeError("--timeout cannot be negative (0 means no limit)")
    return seconds


def main():
    parser = argparse.ArgumentParser(description="Run all evals under evals/")
    parser.add_argument("--json-output", help="Write JSON summary to FILE")
    parser.add_argument(
        "--timeout",
        type=parse_timeout,
        default=DEFAULT_TIMEOUT,
        metavar="SECONDS",
        help=(
            "Wall-clock limit for each eval, in seconds "
            f"(default {DEFAULT_TIMEOUT}; 0 means no limit)"
        ),
    )
    args = parser.parse_args()

    files = discover_eval_files(SCRIPT_DIR)
    if not files:
        print("No eval files (*.py) found under evals/")
        sys.exit(0)

    results = []
    for f in files:
        results.append(run_file(f, timeout=args.timeout))

    all_passed = print_report(results)

    exit_code = 0 if all_passed else 1

    if args.json_output:
        try:
            with open(args.json_output, "w", encoding="utf-8") as fh:
                json.dump({"results": results}, fh, indent=2)
            print(f"Wrote JSON summary to {args.json_output}")
        except Exception as e:
            print(f"Failed to write JSON output: {e}")
            # A lost report is not a clean run: never exit 0 after this.
            if exit_code == 0:
                exit_code = 2

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
