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

Every eval also runs with a fixed seed (DEFAULT_SEED, overridable with
--seed): the child gets PYTHONHASHSEED=<seed>, so str/bytes hashing and set
iteration order are the same on every run, and EVAL_SEED=<seed>, which an eval
that uses random should pass to random.seed(). The seed is recorded in the
JSON summary. Schema change, so RUNNER_VERSION is "0.4".

The JSON summary is checked against evals/last_run.schema.json (a JSON Schema)
right after it is written, by re-reading the file from disk. A summary that
does not match the schema fails the run just like one that was never written.
The validator is a small stdlib one (validate_schema) that supports only the
keywords the schema uses and rejects any other keyword, so the schema cannot
silently be enforced less strictly than it reads.

Usage: python evals/run_all.py [--json-output FILE] [--timeout SECONDS]
                               [--seed N] [--evals-dir DIR]

The run ends with a summary table (status, eval, exit code, time) and a
totals line.

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
import signal

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))

# JSON Schema for the --json-output file. It lives beside the runner and is
# read on every run that writes a summary; a missing schema fails that run.
SCHEMA_FILENAME = "last_run.schema.json"
SCHEMA_PATH = os.path.join(SCRIPT_DIR, SCHEMA_FILENAME)

# Runner version for the summary metadata. Bump when changing output schema.
# 0.3 changes the JSON schema to allow omitting per-result stdout/stderr via
# the --strip-outputs flag; consumers can detect this via summary.outputs_included.
# 0.4 adds summary.seed (the seed every eval ran with) and a JSON Schema,
# evals/last_run.schema.json, that each written summary is validated against.
RUNNER_VERSION = "0.4"

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

# notes/reproducibility-practices.md: "Deterministic seeds: set random.seed(0)
# ... also set PYTHONHASHSEED=0". The runner sets both for every eval.
DEFAULT_SEED = 0
# PYTHONHASHSEED accepts 0..4294967295 and nothing else.
MAX_SEED = 2**32 - 1


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


def eval_env(seed=DEFAULT_SEED):
    """Environment for one eval: the runner's own, plus the fixed seed.

    PYTHONHASHSEED pins str/bytes hashing (and with it set and dict-of-str
    iteration order); EVAL_SEED is what an eval passes to random.seed().
    """
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(seed)
    env["EVAL_SEED"] = str(seed)
    return env


def run_file(
    path,
    timeout=DEFAULT_TIMEOUT,
    max_output_bytes=MAX_CAPTURE_BYTES,
    seed=DEFAULT_SEED,
    root=SCRIPT_DIR,
):
    """Run one eval and return its result dict.

    The eval runs with eval_env(seed). The result's "path" is relative to
    `root`, the directory the evals were discovered in.

    The result always carries duration_seconds: the wall-clock time spent on
    the subprocess, measured with time.perf_counter() and rounded to
    milliseconds. A timed-out or crashed eval is timed too, so a slow failure
    is as visible as a slow pass.

    To avoid unbounded memory growth from evals that print large logs, this
    function redirects stdout/stderr to temporary files on disk and reads back
    up to `max_output_bytes` from each. The returned result includes
    stdout_truncated and stderr_truncated booleans to indicate clipping.
    """
    rel = os.path.relpath(path, start=root)
    started = time.perf_counter()

    def elapsed():
        return round(time.perf_counter() - started, 3)

    # Helper to read up to `max_output_bytes` bytes from a file-like object
    # opened in binary mode, decode with replacement, and indicate whether the
    # content was truncated. If max_output_bytes <= 0 treat it as "no limit"
    # and read the whole file.
    def _read_limited(fh):
        try:
            fh.seek(0)
            if max_output_bytes is None or max_output_bytes <= 0:
                # Read the whole file when no limit is requested.
                data = fh.read()
            else:
                data = fh.read(max_output_bytes + 1)
        except Exception:
            return "", False
        if max_output_bytes is None or max_output_bytes <= 0:
            truncated = False
        else:
            truncated = len(data) > max_output_bytes
            if truncated:
                data = data[:max_output_bytes]
        # Decode bytes to text, replacing invalid sequences
        try:
            if isinstance(data, bytes):
                return data.decode("utf-8", "replace"), truncated
            # Fallback if the file object returned a string for some reason
            return str(data), truncated
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
                env=eval_env(seed),
                start_new_session=True,
            )
            try:
                proc.wait(timeout=timeout)
                timed_out = False
            except subprocess.TimeoutExpired:
                # Try to kill the whole process group (POSIX): this will
                # terminate any children the eval spawned. Fall back to the
                # single-process kill() if that fails (Windows or other errors).
                try:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except Exception:
                        # POSIX group kill failed; fall back to proc.kill()
                        proc.kill()
                except Exception:
                    # Give up on killing the process group and try the old path
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
    return all_passed


def result_status(result):
    """PASS, FAIL or TIMEOUT: the one word a report shows for a result."""
    if result.get("timed_out"):
        return "TIMEOUT"
    if result.get("passed"):
        return "PASS"
    return "FAIL"


def format_summary_table(results):
    """Return the end-of-run table: one row per eval, then a totals line.

    Columns are status, eval path, exit code ("-" when the eval was killed or
    never started) and wall-clock seconds. Failed and timed-out rows are the
    ones a reader is looking for, so the totals line counts them by name.
    """
    headers = ("STATUS", "EVAL", "EXIT", "TIME")
    rows = []
    for r in results:
        code = r.get("returncode")
        duration = r.get("duration_seconds")
        rows.append(
            (
                result_status(r),
                str(r.get("path")),
                "-" if code is None or r.get("timed_out") else str(code),
                f"{duration:.3f}s" if isinstance(duration, (int, float)) else "-",
            )
        )
    widths = [len(h) for h in headers]
    for row in rows:
        widths = [max(w, len(cell)) for w, cell in zip(widths, row)]

    def line(cells):
        status, path, code, timing = cells
        return (
            f"{status:<{widths[0]}}  {path:<{widths[1]}}  "
            f"{code:>{widths[2]}}  {timing:>{widths[3]}}"
        ).rstrip()

    out = [line(headers), line(tuple("-" * w for w in widths))]
    out.extend(line(row) for row in rows)
    passed = sum(1 for r in results if r.get("passed"))
    timed_out = sum(1 for r in results if r.get("timed_out"))
    out.append(
        f"{len(results)} eval(s) in {total_duration_seconds(results):.3f}s total: "
        f"{passed} passed, {len(results) - passed} failed ({timed_out} timed out)"
    )
    return "\n".join(out)


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


def seed_arg(value):
    """--seed accepts an integer PYTHONHASHSEED will take: 0..MAX_SEED."""
    try:
        seed = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"not an integer seed: {value!r}")
    if not 0 <= seed <= MAX_SEED:
        raise argparse.ArgumentTypeError(f"seed must be between 0 and {MAX_SEED}")
    return seed


# JSON Schema keywords validate_schema understands. Annotation keywords carry
# no constraint; any keyword outside both sets is reported as an error rather
# than ignored, so the schema file can never promise more than is checked.
_SCHEMA_ANNOTATIONS = {"$schema", "$id", "title", "description"}
_SCHEMA_KEYWORDS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
    "const",
    "minimum",
    "maximum",
}
# The names _is_type knows; any other "type" value is a schema error.
_SCHEMA_TYPES = {"null", "boolean", "object", "array", "string", "integer", "number"}


def _is_type(value, name):
    """JSON Schema type test. bool is not a number; 2.0 is an integer."""
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if isinstance(value, bool):
        return False
    if name == "integer":
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    if name == "number":
        return isinstance(value, (int, float))
    raise ValueError(f"unknown JSON Schema type {name!r}")


def _json_equal(a, b):
    """Equality as JSON sees it: True is not 1, 1 is 1.0."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    return a == b


def schema_errors(schema, where="$"):
    """Return every problem with `schema` itself, walking all of it.

    Validating an instance only visits the subschemas that instance reaches:
    the items of an empty array, the properties a stripped summary leaves out,
    or a second "type" name behind one that already matched. So the whole
    schema is checked here first, and an unsupported keyword or an unknown
    type name anywhere in it is an error on every run, not only on the rare
    run whose summary happens to reach it.
    """
    errors = []
    unknown = set(schema) - _SCHEMA_KEYWORDS - _SCHEMA_ANNOTATIONS
    if unknown:
        errors.append(f"{where}: schema uses unsupported keyword(s) {sorted(unknown)}")
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        bad = [t for t in types if not isinstance(t, str) or t not in _SCHEMA_TYPES]
        if bad:
            errors.append(f"{where}: unknown JSON Schema type(s) {bad!r}")
    for key, subschema in schema.get("properties", {}).items():
        errors.extend(schema_errors(subschema, f"{where}.{key}"))
    if "items" in schema:
        errors.extend(schema_errors(schema["items"], f"{where}[]"))
    if isinstance(schema.get("additionalProperties"), dict):
        errors.extend(schema_errors(schema["additionalProperties"], f"{where}.*"))
    return errors


def validate_schema(instance, schema, where="$"):
    """Validate `instance` against `schema`; return a list of error strings.

    An empty list means the instance is valid. Each error names the JSON path
    of the offending value ("$.summary.total"), so a failure says what to fix.
    The schema itself is checked first (schema_errors); a schema with problems
    is reported as such and no instance is valid against it.
    """
    problems = schema_errors(schema, where)
    if problems:
        return problems
    return _validate(instance, schema, where)


def _validate(instance, schema, where):
    """validate_schema's recursion, for a schema schema_errors has accepted."""
    errors = []
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(instance, t) for t in types):
            return [f"{where}: expected {' or '.join(types)}, got {type(instance).__name__}"]
    if "const" in schema and not _json_equal(instance, schema["const"]):
        errors.append(f"{where}: expected {schema['const']!r}, got {instance!r}")
    if "enum" in schema and not any(_json_equal(instance, e) for e in schema["enum"]):
        errors.append(f"{where}: {instance!r} is not one of {schema['enum']!r}")

    is_number = isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if is_number and "minimum" in schema and instance < schema["minimum"]:
        errors.append(f"{where}: {instance!r} is less than the minimum {schema['minimum']!r}")
    if is_number and "maximum" in schema and instance > schema["maximum"]:
        errors.append(f"{where}: {instance!r} is greater than the maximum {schema['maximum']!r}")

    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{where}: missing required property {key!r}")
        for key, value in instance.items():
            if key in properties:
                errors.extend(_validate(value, properties[key], f"{where}.{key}"))
                continue
            extra = schema.get("additionalProperties", True)
            if extra is False:
                errors.append(f"{where}: unexpected property {key!r}")
            elif isinstance(extra, dict):
                errors.extend(_validate(value, extra, f"{where}.{key}"))

    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            errors.extend(_validate(item, schema["items"], f"{where}[{i}]"))

    return errors


def validate_json_file(path, schema_path=SCHEMA_PATH):
    """Re-read a written summary from disk and validate it against the schema.

    Returns a list of error strings, empty when the file is valid. A file or
    schema that cannot be read or parsed is an error too, never a pass.
    """
    try:
        with open(schema_path, "r", encoding="utf-8") as fh:
            schema = json.load(fh)
    except (OSError, ValueError) as e:
        return [f"could not load the JSON Schema {schema_path}: {e}"]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            instance = json.load(fh)
    except (OSError, ValueError) as e:
        return [f"could not read back {path}: {e}"]
    try:
        return validate_schema(instance, schema)
    except ValueError as e:
        return [f"the JSON Schema {schema_path} is not usable: {e}"]


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
    parser.add_argument(
        "--seed",
        type=seed_arg,
        default=DEFAULT_SEED,
        metavar="N",
        help=(
            "Seed every eval runs with: exported as PYTHONHASHSEED and "
            f"EVAL_SEED (default: {DEFAULT_SEED})."
        ),
    )
    parser.add_argument(
        "--evals-dir",
        default=SCRIPT_DIR,
        metavar="DIR",
        help="Directory to discover *_eval.py files in (default: this runner's directory).",
    )
    args = parser.parse_args()

    evals_dir = os.path.abspath(args.evals_dir)
    files, skipped_paths = discover_eval_files(evals_dir)
    skipped = [os.path.relpath(p, start=evals_dir) for p in skipped_paths]

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
                seed=args.seed,
            )
        # Already a failed run; a failed summary write cannot make it worse.
        sys.exit(1)

    results = []
    for f in files:
        results.append(
            run_file(
                f,
                timeout=args.timeout,
                max_output_bytes=args.max_output_bytes,
                seed=args.seed,
                root=evals_dir,
            )
        )

    all_passed = print_report(results)
    print_skipped(skipped)
    if skipped:
        print("")
    print(format_summary_table(results))

    json_written = True
    if args.json_output:
        json_written = write_json(
            args.json_output,
            results,
            skipped,
            timeout_seconds=args.timeout,
            include_outputs=not args.strip_outputs,
            seed=args.seed,
        )
        if not json_written:
            print(
                "runner: a JSON summary was requested but not written — "
                "failing the run",
                file=sys.stderr,
            )
        else:
            schema_errors = validate_json_file(args.json_output)
            if schema_errors:
                json_written = False
                print(
                    f"runner: {args.json_output} does not match {SCHEMA_FILENAME} — "
                    "failing the run",
                    file=sys.stderr,
                )
                for err in schema_errors:
                    print(f"  - {err}", file=sys.stderr)
            else:
                print(f"Validated {args.json_output} against {SCHEMA_FILENAME}")

    sys.exit(0 if (all_passed and json_written) else 1)


def write_json(
    path, results, skipped, timeout_seconds=None, include_outputs=True, seed=DEFAULT_SEED
):
    """Write the JSON output containing results, skipped and a summary object.

    The summary includes:
    - all_passed (bool): True only if there was at least one result and all passed
    - total (int), passed (int), failed (int), timed_out (int)
    - timeout_seconds (float or null): the per-eval timeout used (if known)
    - total_duration_seconds (float): the sum of every result's
      duration_seconds, 0.0 when nothing ran
    - seed (int): the seed every eval ran with (PYTHONHASHSEED and EVAL_SEED)
    - runner_version (string), outputs_included (bool) and timestamp (ISO8601 UTC string)

    The shape is pinned by evals/last_run.schema.json; main() validates the
    written file against it (validate_json_file).

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
        "seed": seed,
        "runner_version": RUNNER_VERSION,
        "outputs_included": bool(include_outputs),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
        # Atomically replace the target with the newly-written temp file.
        os.replace(tmp_path, path)
        tmp_path = None
        # Attempt to make the rename durable by fsyncing the parent directory.
        # Some platforms and filesystems only guarantee the directory entry is
        # persisted once the directory itself is synced. This is a best-effort
        # durability improvement: if the operation is unsupported or fails we
        # silently fall back to the previous behaviour so the runner remains
        # portable.
        try:
            try:
                # Open the directory read-only and fsync its descriptor.
                dirfd = os.open(directory, os.O_RDONLY)
            except Exception:
                dirfd = None
            if dirfd is not None:
                try:
                    os.fsync(dirfd)
                finally:
                    try:
                        os.close(dirfd)
                    except Exception:
                        pass
        except Exception:
            # Give up on directory fsync; don't fail the write for portability.
            pass
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
