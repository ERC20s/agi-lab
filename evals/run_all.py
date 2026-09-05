"""
A tiny, dependency-free eval runner for agi-lab.

Discovers eval scripts under the same directory (evals/) and executes
each with the same Python interpreter. Exit code 0 means success.

Only files named *_eval.py are executed, matching CONTRIBUTING.md
("Location and filename: evals/<topic>_eval.py"). Any other .py file in
evals/ — a shared helper module, a scratch file — is skipped, listed as
[SKIP] and never affects the exit code.

Every eval runs with stdin closed (subprocess.DEVNULL) and under a wall-clock
timeout (DEFAULT_TIMEOUT seconds, overridable with --timeout), so one eval that
loops for ever or waits on input() cannot hang the whole run. A timed-out eval
is reported as [TIMEOUT] and counts as a failure.

Every eval is also timed: each result carries duration_seconds (wall-clock
seconds, sub-second precision, measured around the subprocess and so including
interpreter start-up), and the JSON summary carries total_duration_seconds.
Evals here are meant to stay small and fast; the numbers are how a slow one
gets noticed. Schema change, so RUNNER_VERSION is "0.2".

Usage: python evals/run_all.py [--json-output FILE] [--timeout SECONDS]

By default this prints a human-readable per-file report and exits
with 0 if all evals passed, or 1 if any failed, timed out, or if no
eval files were found at all.

A requested --json-output that could not be written is a failed run: the
summary is what other tools read, so a run that never wrote it must not
report green. The file is also replaced atomically (written next to the
target, then os.replace()d over it), so a failure mid-write leaves the
previous evals/last_run.json intact rather than a truncated one.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import datetime

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))

# Runner version for the summary metadata. Bump when changing output schema.
# 0.3 changes the JSON schema to allow omitting per-result stdout/stderr via
# the --strip-outputs flag; consumers can detect this via summary.outputs_included.
RUNNER_VERSION = "0.3"

# An eval is a named thing: CONTRIBUTING.md says evals/<topic>_eval.py.
EVAL_SUFFIX = "_eval.py"

# notes/reproducibility-practices.md tells contributors to bound a subprocess
# with timeout=SECONDS; the runner holds itself to the same rule. Evals here are
# meant to finish in well under a second, so a minute is a generous ceiling.
DEFAULT_TIMEOUT = 60

# Maximum bytes to read back from each eval's stdout/stderr. A malicious or
# buggy eval that prints megabytes cannot exhaust the runner's memory when
# output is streamed to temporary files on disk; the runner truncates what it
# returns. Default 100KiB, configurable with --max-output-bytes.
MAX_CAPTURE_BYTES = 100 * 1024


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


def _partial(stream):
    """TimeoutExpired carries whatever was captured before the kill (or None)."""
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode("utf-8", "replace")
    return stream


def run_file(path, timeout=DEFAULT_TIMEOUT, max_output_bytes=MAX_CAPTURE_BYTES):
    """Run one eval and return its result dict.

    The result always carries duration_seconds: the wall-clock time spent on
    the subprocess, measured with time.perf_counter() and rounded to
    milliseconds. A timed-out or crashed eval is timed too, so a slow failure
    is as visible as a slow pass.

    To avoid unbounded memory growth from evals that print large logs, this
    function redirects stdout/stderr to temporary files on disk and reads back
    up to `max_output_bytes` from each. The returned result includes
    stdout_truncated and stderr_truncated booleans to indicate clipping.
    """
    rel = os.path.relpath(path, start=SCRIPT_DIR)
    started = time.perf_counter()

    def elapsed():
        return round(time.perf_counter() - started, 3)

    # Helper to read at most `max_output_bytes` bytes from a file-like object
    # opened in binary mode, decode with replacement, and indicate whether the
    # content was truncated.
    def _read_limited(fh):
        try:
            fh.seek(0)
            data = fh.read(max_output_bytes + 1)
        except Exception:
            return "", False
        truncated = len(data) > max_output_bytes
        if truncated:
            data = data[:max_output_bytes]
        # Decode bytes to text, replacing invalid sequences
        try:
            return data.decode("utf-8", "replace"), truncated
        except Exception:
            return "", truncated

    stdout_truncated = False
    stderr_truncated = False

    # Use TemporaryFile so large outputs go to disk and do not exhaust memory.
    with tempfile.TemporaryFile() as out_fh, tempfile.TemporaryFile() as err_fh:
        try:
            proc = subprocess.Popen(
                [sys.executable, path],
                stdout=out_fh,
                stderr=err_fh,
                stdin=subprocess.DEVNULL,
            )
            try:
                proc.wait(timeout=timeout)
                timed_out = False
            except subprocess.TimeoutExpired:
                # Kill the process and mark timeout
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
                timed_out = True

            returncode = proc.returncode

            # Read back outputs limited by the cap
            out_text, out_trunc = _read_limited(out_fh)
            err_text, err_trunc = _read_limited(err_fh)
            stdout_truncated = out_trunc
            stderr_truncated = err_trunc

            if timed_out:
                # Append a timeout note to stderr to be consistent with previous
                # behaviour which included such a message in the TimeoutExpired
                # exception handling path.
                err_text = (
                    err_text
                    + ("\n" if err_text and not err_text.endswith("\n") else "")
                    + f"runner: {rel} exceeded the {timeout}s timeout and was killed\n"
                )

            return {
                "path": rel,
                "returncode": returncode,
                "stdout": out_text,
                "stderr": err_text,
                "passed": returncode == 0,
                "timed_out": timed_out,
                "duration_seconds": elapsed(),
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            }
        except Exception as e:
            return {
                "path": rel,
                "returncode": None,
                "stdout": "",
                "stderr": f"runner error: {e}",
                "passed": False,
                "timed_out": False,
                "duration_seconds": elapsed(),
                "stdout_truncated": False,
                "stderr_truncated": False,
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
        duration = r.get("duration_seconds")
        timing = f", {duration:.3f}s" if isinstance(duration, (int, float)) else ""
        print(f"[{status}] {r.get('path')} (exit={code}{timing})")
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
    total_duration = total_duration_seconds(results)
    if results:
        print(f"{len(results)} eval(s) in {total_duration:.3f}s total")
    return all_passed


def total_duration_seconds(results):
    """Sum the per-eval durations, ignoring any result that has none."""
    total = 0.0
    for r in results:
        duration = r.get("duration_seconds")
        if isinstance(duration, (int, float)):
            total += float(duration)
    return round(total, 3)


def print_skipped(skipped):
    """List the .py files that were found but are not evals. Never fails a run."""
    for path in skipped:
        print(f"[SKIP] {path} (not *{EVAL_SUFFIX})")


def positive_timeout(value):
    """--timeout accepts a number of seconds greater than zero."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"not a number of seconds: {value!r}")
    if seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be greater than 0 seconds")
    return seconds


def main():
    parser = argparse.ArgumentParser(description="Run all evals under evals/")
    parser.add_argument("--json-output", help="Write JSON summary to FILE")
    parser.add_argument(
        "--timeout",
        type=positive_timeout,
        default=DEFAULT_TIMEOUT,
        metavar="SECONDS",
        help=(
            "Wall-clock limit for each eval, in seconds "
            f"(default: {DEFAULT_TIMEOUT}). An eval that exceeds it is killed "
            "and reported as [TIMEOUT]."
        ),
    )
    parser.add_argument(
        "--max-output-bytes",
        type=int,
        default=MAX_CAPTURE_BYTES,
        metavar="BYTES",
        help=(
            "Maximum number of bytes to read back from each eval's stdout and "
            "stderr. Larger output is truncated; set to 0 for no limit. "
            f"(default: {MAX_CAPTURE_BYTES})."
        ),
    )
    parser.add_argument(
        "--strip-outputs",
        action="store_true",
        help=(
            "When set, omit per-result 'stdout' and 'stderr' fields from the "
            "written JSON summary and set summary.outputs_included to false. "
            "Default is to include outputs."
        ),
    )
    args = parser.parse_args()

    files, skipped_paths = discover_eval_files(SCRIPT_DIR)
    skipped = [os.path.relpath(p, start=SCRIPT_DIR) for p in skipped_paths]

    if not files:
        # Nothing ran, so nothing passed: a repository whose evals all vanished
        # must not report green.
        print(f"No eval files (*{EVAL_SUFFIX}) found under evals/ — nothing was run.")
        print_skipped(skipped)
        if args.json_output:
            write_json(
                args.json_output,
                [],
                skipped,
                timeout_seconds=args.timeout,
                include_outputs=not args.strip_outputs,
            )
        # Already a failed run; a failed summary write cannot make it worse.
        sys.exit(1)

    results = []
    for f in files:
        results.append(run_file(f, timeout=args.timeout, max_output_bytes=args.max_output_bytes))

    all_passed = print_report(results)
    print_skipped(skipped)

    json_written = True
    if args.json_output:
        json_written = write_json(
            args.json_output,
            results,
            skipped,
            timeout_seconds=args.timeout,
            include_outputs=not args.strip_outputs,
        )
        if not json_written:
            print(
                "runner: a JSON summary was requested but not written — "
                "failing the run",
                file=sys.stderr,
            )

    sys.exit(0 if (all_passed and json_written) else 1)


def write_json(path, results, skipped, timeout_seconds=None, include_outputs=True):
    """Write the JSON output containing results, skipped and a summary object.

    The summary includes:
    - all_passed (bool): True only if there was at least one result and all passed
    - total (int), passed (int), failed (int), timed_out (int)
    - timeout_seconds (float or null): the per-eval timeout used (if known)
    - total_duration_seconds (float): the sum of every result's
      duration_seconds, 0.0 when nothing ran
    - runner_version (string), outputs_included (bool) and timestamp (ISO8601 UTC string)

    Each entry of results also carries duration_seconds (float), the
    wall-clock time that eval took. When include_outputs is false, per-result
    fields 'stdout' and 'stderr' are removed from each result before
    serialisation; callers should set include_outputs=False when they want a
    smaller or redacted summary.

    Returns True when the file is on disk, False when it is not — the reason
    goes to stderr. Nothing is raised: a caller decides what a failed write
    means (main() makes it a non-zero exit).

    The write is atomic. The payload is serialised in memory first, written to
    a temporary file in the target's own directory, flushed, and only then
    os.replace()d over the target. So the file at `path` is either the previous
    run or this one, never half of either.
    """
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    timed_out = sum(1 for r in results if r.get("timed_out"))
    all_passed = (total > 0) and (passed == total)
    # Decide whether to include per-result outputs. If include_outputs is
    # False, create a shallow copy of each result with stdout/stderr removed so
    # the on-disk JSON omits potentially large strings.
    if not include_outputs:
        serialisable_results = []
        for r in results:
            # Copy only the fields we want to keep: everything except stdout/stderr
            r_copy = {k: v for k, v in r.items() if k not in ("stdout", "stderr")}
            serialisable_results.append(r_copy)
    else:
        serialisable_results = results

    summary = {
        "all_passed": all_passed,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "timed_out": timed_out,
        "timeout_seconds": float(timeout_seconds) if timeout_seconds is not None else None,
        "total_duration_seconds": total_duration_seconds(results),
        "runner_version": RUNNER_VERSION,
        "outputs_included": bool(include_outputs),
        "timestamp": datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat(),
    }

    tmp_path = None
    try:
        # Serialise before touching the filesystem: an unserialisable payload
        # must not cost us the existing file.
        payload = json.dumps(
            {"results": serialisable_results, "skipped": skipped, "summary": summary}, indent=2
        )

        directory = os.path.dirname(os.path.abspath(path))
        # A named parent that does not exist yet is created; an existing one is
        # left alone. os.makedirs raises here if the parent is a regular file,
        # which is exactly the failure this function is meant to report.
        os.makedirs(directory, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(
            prefix=os.path.basename(path) + ".", suffix=".tmp", dir=directory
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
        tmp_path = None
        print(f"Wrote JSON summary to {path}")
        return True
    except Exception as e:
        print(f"Failed to write JSON output to {path}: {e}", file=sys.stderr)
        return False
    finally:
        # A temporary file only survives if the replace never happened.
        if tmp_path is not None:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


if __name__ == "__main__":
    main()
