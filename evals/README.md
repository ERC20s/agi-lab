Eval files

- Place small, runnable Python scripts under evals/ named evals/<topic>_eval.py
  (the filename rule in CONTRIBUTING.md). Only files ending in _eval.py are run.
- Eval scripts must use the Python standard library only and should be runnable
  with `python path/to/eval.py`.
- A script should perform its checks and exit with code 0 on success and non-zero
  on failure. It may print a short, human-readable summary to stdout and any
  diagnostics to stderr.

Repository-wide eval: evals/note-coverage_eval.py

- Most evals here validate one hard-coded note. note-coverage_eval.py validates
  the set: it walks notes/*.md and evals/*_eval.py, derives the topic from each
  filename and fails when a note has no evals/<topic>_eval.py, when an eval has
  no notes/<topic>.md, or when an evals/... path named in a note's Eval section
  does not exist. It prints one OK/FAIL line per topic, so a failure names the
  file to fix.
- It follows the same contract as every other eval (stdlib only, module
  docstring, main() harness, exit 0 on success and non-zero on failure) and is
  discovered by run_all.py like any other *_eval.py.
- A meta-eval checks the repository rather than a single note, so it is exempt
  from needing a note of its own. The exemptions are the filenames in the
  META_EVALS set at the top of note-coverage_eval.py; add a new meta-eval's
  filename there.

Runner: evals/run_all.py

- Purpose: discover and execute eval scripts under evals/ and report per-file
  pass/fail status based on exit codes.
- Usage: python evals/run_all.py [--json-output FILE] [--timeout SECONDS]
- Discovery rule: only files whose name ends in _eval.py are executed. The
  runner itself, __init__.py and __pycache__ are excluded as before. Any other
  .py file under evals/ — a shared helper module, a scratch file — is skipped:
  it is never executed, never counted as a pass, and never fails the run.
- Skipped files are listed after the report, one line each:
  `[SKIP] note_checks.py (not *_eval.py)`, so nothing disappears silently.
  Renaming a file to <topic>_eval.py puts it back in the run.
- The runner executes each eval as a separate process (same Python interpreter),
  captures stdout/stderr and returns exit code 0 if all evals passed, else 1.
- Per-eval timeout: each eval is given DEFAULT_TIMEOUT seconds (60) of wall
  clock; --timeout SECONDS overrides it (any number greater than 0). An eval
  that exceeds the limit is killed, reported as
  `[TIMEOUT] slow_eval.py (exit=None)` with a stderr line naming the file and
  the limit, and counts as a failure, so the run still exits 1.
- Closed stdin: every eval runs with stdin=subprocess.DEVNULL. An eval that
  reads input() fails fast instead of waiting for a keystroke nobody can type —
  the runner captures output, so a prompt would never be seen. This matches the
  guidance in notes/reproducibility-practices.md ("use subprocess.run(...,
  timeout=SECONDS)").
- Exit codes: 0 when every discovered eval passed; 1 when any eval failed or
  timed out, and 1 when no *_eval.py files were found at all — nothing ran, so
  nothing passed, and an empty evals/ must not report green.
- The --json-output FILE option writes an aggregated JSON summary with two keys:
  "results" (one object per executed eval: path, returncode, stdout, stderr,
  passed boolean, timed_out boolean) and "skipped" (the paths of the .py files
  that were not run). For a timed-out eval returncode is null, timed_out is
  true, and stdout/stderr hold whatever was captured before the kill.

Notes and security

- The runner executes code on the local machine; evaluators should not run
  untrusted code. Use CI isolation or sandboxing as appropriate.
- The contract is intentionally small to reduce maintenance burden.
