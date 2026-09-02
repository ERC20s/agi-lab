"""
A tiny, dependency-free eval runner for agi-lab.

Discovers eval scripts under the same directory (evals/) and executes
each with the same Python interpreter. Exit code 0 means success.

Only files named *_eval.py are executed, matching CONTRIBUTING.md
("Location and filename: evals/<topic>_eval.py"). Any other .py file in
evals/ — a shared helper module, a scratch file — is skipped, listed as
[SKIP] and never affects the exit code.

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

# An eval is a named thing: CONTRIBUTING.md says evals/<topic>_eval.py.
EVAL_SUFFIX = "_eval.py"


def discover_eval_files(root_dir):
    """Return (eval_files, skipped_files).

    eval_files are the *_eval.py scripts the runner executes; skipped_files
    are the other .py files found under evals/ (helper modules, scratch
    files), reported but never run.
    """
    files = []
    skipped = []
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
            # Only *_eval.py is an eval; everything else is a helper, not a run.
            if not fn.endswith(EVAL_SUFFIX):
                skipped.append(full)
                continue
            files.append(full)
    files.sort()
    skipped.sort()
    return files, skipped


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


def print_skipped(skipped):
    """List the .py files that were found but are not evals. Never fails a run."""
    for path in skipped:
        print(f"[SKIP] {path} (not *{EVAL_SUFFIX})")


def main():
    parser = argparse.ArgumentParser(description="Run all evals under evals/")
    parser.add_argument("--json-output", help="Write JSON summary to FILE")
    args = parser.parse_args()

    files, skipped_paths = discover_eval_files(SCRIPT_DIR)
    skipped = [os.path.relpath(p, start=SCRIPT_DIR) for p in skipped_paths]

    if not files:
        print(f"No eval files (*{EVAL_SUFFIX}) found under evals/")
        print_skipped(skipped)
        if args.json_output:
            write_json(args.json_output, [], skipped)
        sys.exit(0)

    results = []
    for f in files:
        results.append(run_file(f))

    all_passed = print_report(results)
    print_skipped(skipped)

    if args.json_output:
        write_json(args.json_output, results, skipped)

    sys.exit(0 if all_passed else 1)


def write_json(path, results, skipped):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"results": results, "skipped": skipped}, fh, indent=2)
        print(f"Wrote JSON summary to {path}")
    except Exception as e:
        print(f"Failed to write JSON output: {e}")


if __name__ == "__main__":
    main()
