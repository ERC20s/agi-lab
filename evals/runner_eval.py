"""Self-test for the eval runner itself, evals/run_all.py.

Usage: python3 evals/runner_eval.py

Every eval in this repository depends on run_all.py, and run_all.py is the one
file nothing checked: it excludes itself from discovery by design ("Exclude this
runner file itself", plus the rule that only *_eval.py is executed), so a
regression in discover_eval_files or write_json would show up as a green run.
This meta-eval closes that gap.

It loads evals/run_all.py by path with importlib.util.spec_from_file_location —
no new import name, no third-party dependency — and exercises its functions
against throwaway fixtures built with tempfile:

- discover_eval_files returns only *_eval.py, lists other .py files as skipped,
  and puts neither __init__.py nor anything under __pycache__/ in either list;
- run_file on a script that exits 3 reports passed False, returncode 3 and a
  numeric duration_seconds;
- run_file with a short timeout on a sleeping script reports timed_out True and
  a stderr mentioning "exceeded the";
- run_file on a script that calls input() fails instead of hanging, because the
  runner passes stdin=subprocess.DEVNULL;
- write_json writes parsable JSON whose summary carries all_passed, total,
  passed, failed, timed_out, timeout_seconds, total_duration_seconds,
  runner_version and timestamp, and returns True;
- write_json creates a missing parent directory for the output file;
- write_json returns False (it does not raise) when the output path is
  impossible, e.g. its parent is an existing regular file;
- a failed write leaves an existing, valid last_run.json byte-for-byte intact
  and leaves no temporary file behind, because the payload is serialised first
  and swapped in with os.replace();
- positive_timeout accepts "1.5" and rejects "0", "-1" and "abc".

Fixtures are created in a temporary directory inside the repository root (so
run_file's os.path.relpath never has to cross a drive on Windows) and are
removed again; the directory name starts with a dot and lives outside evals/, so
the runner never discovers it.

Prints one OK/FAIL line per check. Returns 0 when every check passes, 1 when any
check fails, 2 when evals/run_all.py cannot be loaded at all.
"""

import argparse
import importlib.util
import json
import os
import sys
import tempfile

# This eval checks the repository as a whole, not one note: it is exempt from
# the notes/<topic>.md pairing rule and says so here, where
# evals/note-coverage_eval.py reads it (declares_meta_eval).
META_EVAL = True

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVALS_DIR = os.path.join(ROOT, "evals")
RUNNER_PATH = os.path.join(EVALS_DIR, "run_all.py")

# Generous ceilings: these fixtures exit immediately, the sleeper is meant to be
# killed. Kept well apart so a loaded machine does not flip the timeout check.
FIXTURE_TIMEOUT = 30
SHORT_TIMEOUT = 0.5
SLEEP_SECONDS = 5


def load_runner(path=RUNNER_PATH):
    """Import evals/run_all.py by path, under a name of its own."""
    spec = importlib.util.spec_from_file_location("agi_lab_run_all_under_test", path)
    if spec is None or spec.loader is None:
        raise ImportError("could not build an import spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def temp_workspace():
    """A throwaway directory, preferably on the same drive as the repository."""
    try:
        return tempfile.TemporaryDirectory(prefix=".runner_eval_", dir=ROOT)
    except OSError:
        return tempfile.TemporaryDirectory(prefix="runner_eval_")


def write_script(directory, name, body):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


def basenames(paths):
    return sorted(os.path.basename(p) for p in paths)


def check_discovery(runner):
    """Only *_eval.py runs; other .py files are skipped; noise is ignored."""
    with temp_workspace() as tmp:
        write_script(tmp, "alpha_eval.py", "print('alpha')\n")
        write_script(tmp, "helper.py", "VALUE = 1\n")
        write_script(tmp, "__init__.py", "")
        write_script(tmp, "notes.txt", "not python\n")
        cache = os.path.join(tmp, "__pycache__")
        os.makedirs(cache)
        write_script(cache, "cached_eval.py", "print('cached')\n")
        write_script(cache, "junk.py", "")

        files, skipped = runner.discover_eval_files(tmp)

    problems = []
    if basenames(files) != ["alpha_eval.py"]:
        problems.append("eval files were %s, expected ['alpha_eval.py']" % basenames(files))
    if basenames(skipped) != ["helper.py"]:
        problems.append("skipped files were %s, expected ['helper.py']" % basenames(skipped))
    if problems:
        return False, "; ".join(problems)
    return True, "alpha_eval.py runs, helper.py is skipped, __init__.py and __pycache__/ are ignored"


def check_failing_exit_code(runner):
    """A non-zero exit is a failure, and it is timed."""
    with temp_workspace() as tmp:
        path = write_script(tmp, "boom_eval.py", "import sys\nsys.exit(3)\n")
        result = runner.run_file(path, timeout=FIXTURE_TIMEOUT)

    problems = []
    if result.get("passed") is not False:
        problems.append("passed was %r, expected False" % result.get("passed"))
    if result.get("returncode") != 3:
        problems.append("returncode was %r, expected 3" % result.get("returncode"))
    if result.get("timed_out") is not False:
        problems.append("timed_out was %r, expected False" % result.get("timed_out"))
    duration = result.get("duration_seconds")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration < 0:
        problems.append("duration_seconds was %r, expected a number >= 0" % duration)
    if problems:
        return False, "; ".join(problems)
    return True, "exit 3 gives passed=False, returncode=3, duration_seconds=%.3fs" % float(duration)


def check_timeout(runner):
    """A script that never finishes is killed and reported as a timeout."""
    with temp_workspace() as tmp:
        path = write_script(
            tmp,
            "sleepy_eval.py",
            "import time\ntime.sleep(%d)\n" % SLEEP_SECONDS,
        )
        result = runner.run_file(path, timeout=SHORT_TIMEOUT)

    problems = []
    if result.get("timed_out") is not True:
        problems.append("timed_out was %r, expected True" % result.get("timed_out"))
    if result.get("passed") is not False:
        problems.append("passed was %r, expected False" % result.get("passed"))
    if "exceeded the" not in (result.get("stderr") or ""):
        problems.append("stderr did not mention the timeout: %r" % result.get("stderr"))
    if problems:
        return False, "; ".join(problems)
    return True, "a %ss sleep under a %ss timeout is killed and reported as [TIMEOUT]" % (
        SLEEP_SECONDS,
        SHORT_TIMEOUT,
    )


def check_stdin_closed(runner):
    """An eval that reads stdin fails immediately instead of waiting for ever."""
    with temp_workspace() as tmp:
        path = write_script(tmp, "prompt_eval.py", "answer = input()\nprint(answer)\n")
        result = runner.run_file(path, timeout=FIXTURE_TIMEOUT)

    problems = []
    if result.get("timed_out") is not False:
        problems.append("the run hit the timeout instead of failing on closed stdin")
    if result.get("passed") is not False:
        problems.append("passed was %r, expected False" % result.get("passed"))
    if problems:
        return False, "; ".join(problems)
    return True, "input() fails fast (stdin=DEVNULL), returncode=%r" % result.get("returncode")


def check_write_json(runner):
    """The JSON summary keeps the schema consumers were promised."""
    results = [
        {
            "path": "alpha_eval.py",
            "returncode": 0,
            "stdout": "ok\n",
            "stderr": "",
            "passed": True,
            "timed_out": False,
            "duration_seconds": 0.25,
        },
        {
            "path": "beta_eval.py",
            "returncode": None,
            "stdout": "",
            "stderr": "runner: beta_eval.py exceeded the 1.5s timeout and was killed\n",
            "passed": False,
            "timed_out": True,
            "duration_seconds": 1.5,
        },
    ]

    with temp_workspace() as tmp:
        out = os.path.join(tmp, "last_run.json")
        returned = runner.write_json(out, results, ["helper.py"], timeout_seconds=1.5)
        if not os.path.isfile(out):
            return False, "write_json wrote no file at %s" % out
        with open(out, "r", encoding="utf-8") as fh:
            payload = json.load(fh)

    problems = []
    if returned is not True:
        problems.append("write_json returned %r on success, expected True" % returned)
    for key in ("results", "skipped", "summary"):
        if key not in payload:
            problems.append("top-level key %r is missing" % key)
    summary = payload.get("summary") or {}
    expected_keys = [
        "all_passed",
        "total",
        "passed",
        "failed",
        "timed_out",
        "timeout_seconds",
        "total_duration_seconds",
        "runner_version",
        "timestamp",
    ]
    for key in expected_keys:
        if key not in summary:
            problems.append("summary is missing %r" % key)
    expected_values = {
        "all_passed": False,
        "total": 2,
        "passed": 1,
        "failed": 1,
        "timed_out": 1,
        "timeout_seconds": 1.5,
        "total_duration_seconds": 1.75,
    }
    for key, want in expected_values.items():
        if key in summary and summary[key] != want:
            problems.append("summary[%r] was %r, expected %r" % (key, summary[key], want))
    if summary.get("runner_version") != getattr(runner, "RUNNER_VERSION", None):
        problems.append(
            "summary['runner_version'] was %r, expected %r"
            % (summary.get("runner_version"), getattr(runner, "RUNNER_VERSION", None))
        )
    if not isinstance(summary.get("timestamp"), str) or not summary.get("timestamp"):
        problems.append("summary['timestamp'] was %r, expected a non-empty string" % summary.get("timestamp"))
    if payload.get("skipped") != ["helper.py"]:
        problems.append("skipped was %r, expected ['helper.py']" % payload.get("skipped"))
    if problems:
        return False, "; ".join(problems)
    return True, "summary carries the v%s schema (%d fields checked)" % (
        summary.get("runner_version"),
        len(expected_keys),
    )


def sample_results():
    """One passing result, enough for a valid summary."""
    return [
        {
            "path": "alpha_eval.py",
            "returncode": 0,
            "stdout": "ok\n",
            "stderr": "",
            "passed": True,
            "timed_out": False,
            "duration_seconds": 0.1,
        }
    ]


def check_write_json_creates_parent(runner):
    """--json-output may name a directory that does not exist yet."""
    with temp_workspace() as tmp:
        out = os.path.join(tmp, "reports", "nested", "last_run.json")
        returned = runner.write_json(out, sample_results(), [], timeout_seconds=1.0)
        exists = os.path.isfile(out)
        parsable = False
        if exists:
            try:
                with open(out, "r", encoding="utf-8") as fh:
                    json.load(fh)
                parsable = True
            except Exception:
                parsable = False

    problems = []
    if returned is not True:
        problems.append("write_json returned %r, expected True" % returned)
    if not exists:
        problems.append("no file was written under the missing parent directory")
    elif not parsable:
        problems.append("the file written under the new directory is not valid JSON")
    if problems:
        return False, "; ".join(problems)
    return True, "a missing parent directory is created and the summary lands in it"


def check_write_json_failure_returns_false(runner):
    """An impossible output path is reported, not raised."""
    with temp_workspace() as tmp:
        blocker = write_script(tmp, "blocker", "not a directory\n")
        out = os.path.join(blocker, "last_run.json")
        try:
            returned = runner.write_json(out, sample_results(), [], timeout_seconds=1.0)
        except Exception as exc:
            return False, "write_json raised %s instead of returning False: %s" % (
                type(exc).__name__,
                exc,
            )
        wrote_anything = os.path.isfile(out)

    problems = []
    if returned is not False:
        problems.append("write_json returned %r for an impossible path, expected False" % returned)
    if wrote_anything:
        problems.append("a file appeared at %s, which should not be writable" % out)
    if problems:
        return False, "; ".join(problems)
    return True, "a path whose parent is a regular file returns False without raising"


def check_write_json_leaves_existing_file_intact(runner):
    """A failed write must not cost the group its previous last_run.json."""
    with temp_workspace() as tmp:
        out = os.path.join(tmp, "last_run.json")
        first = runner.write_json(out, sample_results(), [], timeout_seconds=1.0)
        with open(out, "r", encoding="utf-8") as fh:
            before = fh.read()

        # A payload json.dumps cannot serialise: the failure happens before the
        # target is touched, which is the point of writing to a temp file first.
        poisoned = sample_results()
        poisoned[0]["stdout"] = {1, 2, 3}
        try:
            second = runner.write_json(out, poisoned, [], timeout_seconds=1.0)
        except Exception as exc:
            return False, "write_json raised %s instead of returning False: %s" % (
                type(exc).__name__,
                exc,
            )

        with open(out, "r", encoding="utf-8") as fh:
            after = fh.read()
        leftovers = [n for n in os.listdir(tmp) if n != "last_run.json"]

    problems = []
    if first is not True:
        problems.append("the first write returned %r, expected True" % first)
    if second is not False:
        problems.append("the failed write returned %r, expected False" % second)
    if after != before:
        problems.append("last_run.json changed after a failed write")
    else:
        try:
            json.loads(after)
        except Exception as exc:
            problems.append("last_run.json is no longer valid JSON: %s" % exc)
    if leftovers:
        problems.append("temporary files were left behind: %s" % sorted(leftovers))
    if problems:
        return False, "; ".join(problems)
    return True, "a failed write leaves the previous summary intact and no temp file behind"


def check_positive_timeout(runner):
    """--timeout only accepts a number of seconds greater than zero."""
    problems = []
    try:
        value = runner.positive_timeout("1.5")
        if value != 1.5:
            problems.append("positive_timeout('1.5') returned %r, expected 1.5" % value)
    except argparse.ArgumentTypeError as exc:
        problems.append("positive_timeout('1.5') was rejected: %s" % exc)

    for bad in ("0", "-1", "abc"):
        try:
            runner.positive_timeout(bad)
        except argparse.ArgumentTypeError:
            continue
        problems.append("positive_timeout(%r) was accepted, expected a rejection" % bad)

    if problems:
        return False, "; ".join(problems)
    return True, "'1.5' accepted; '0', '-1' and 'abc' rejected"


CHECKS = (
    ("discover_eval_files", check_discovery),
    ("run_file exit code", check_failing_exit_code),
    ("run_file timeout", check_timeout),
    ("run_file closed stdin", check_stdin_closed),
    ("write_json schema", check_write_json),
    ("write_json creates parent", check_write_json_creates_parent),
    ("write_json reports failure", check_write_json_failure_returns_false),
    ("write_json is atomic", check_write_json_leaves_existing_file_intact),
    ("positive_timeout", check_positive_timeout),
)


def main():
    if not os.path.isfile(RUNNER_PATH):
        print("ERROR: expected the runner at evals/run_all.py", file=sys.stderr)
        return 2

    try:
        runner = load_runner()
    except Exception as exc:
        print("ERROR: could not load evals/run_all.py: %s: %s" % (type(exc).__name__, exc),
              file=sys.stderr)
        return 2

    failures = 0
    for name, check in CHECKS:
        try:
            ok, detail = check(runner)
        except Exception as exc:
            ok, detail = False, "raised %s: %s" % (type(exc).__name__, exc)
        print("%s: %s - %s" % ("OK" if ok else "FAIL", name, detail))
        if not ok:
            failures += 1

    print("")
    print("checks: %d, failed: %d" % (len(CHECKS), failures))

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
