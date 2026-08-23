"""
A tiny, dependency-free eval runner for agi-lab.

Discovers Python files under the same directory (evals/) and executes
each with the same Python interpreter. Exit code 0 means success.

Usage: python evals/run_all.py [--json-output FILE]

By default this prints a human-readable per-file report and exits
with 0 if all evals passed, or 1 if any failed.
"""
import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))


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


def run_file(path):
    try:
        proc = subprocess.run([sys.executable, path], capture_output=True, text=True)
        return {
            "path": os.path.relpath(path, start=SCRIPT_DIR),
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "passed": proc.returncode == 0,
        }
    except Exception as e:
        return {
            "path": os.path.relpath(path, start=SCRIPT_DIR),
            "returncode": None,
            "stdout": "",
            "stderr": f"runner error: {e}",
            "passed": False,
        }


def print_report(results):
    all_passed = True
    for r in results:
        status = "PASS" if r.get("passed") else "FAIL"
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
    return all_passed


def main():
    parser = argparse.ArgumentParser(description="Run all evals under evals/")
    parser.add_argument("--json-output", help="Write JSON summary to FILE")
    args = parser.parse_args()

    files = discover_eval_files(SCRIPT_DIR)
    if not files:
        print("No eval files (*.py) found under evals/")
        sys.exit(0)

    results = []
    for f in files:
        results.append(run_file(f))

    all_passed = print_report(results)

    if args.json_output:
        try:
            with open(args.json_output, "w", encoding="utf-8") as fh:
                json.dump({"results": results}, fh, indent=2)
            print(f"Wrote JSON summary to {args.json_output}")
        except Exception as e:
            print(f"Failed to write JSON output: {e}")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
