Eval files

- Place small, runnable Python scripts under evals/ named evals/<topic>_eval.py
  (the filename rule in CONTRIBUTING.md). Only files ending in _eval.py are run.
- Eval scripts must use the Python standard library only and should be runnable
  with `python path/to/eval.py`.
- A script should perform its checks and exit with code 0 on success and non-zero
  on failure. It may print a short, human-readable summary to stdout and any
  diagnostics to stderr.

Runner: evals/run_all.py

- Purpose: discover and execute eval scripts under evals/ and report per-file
  pass/fail status based on exit codes.
- Usage: python evals/run_all.py [--json-output FILE]
- Discovery rule: only files whose name ends in _eval.py are executed. The
  runner itself, __init__.py and __pycache__ are excluded as before. Any other
  .py file under evals/ — a shared helper module, a scratch file — is skipped:
  it is never executed, never counted as a pass, and never fails the run.
- Skipped files are listed after the report, one line each:
  `[SKIP] note_checks.py (not *_eval.py)`, so nothing disappears silently.
  Renaming a file to <topic>_eval.py puts it back in the run.
- The runner executes each eval as a separate process (same Python interpreter),
  captures stdout/stderr and returns exit code 0 if all evals passed, else 1.
- The --json-output FILE option writes an aggregated JSON summary with two keys:
  "results" (one object per executed eval: path, returncode, stdout, stderr,
  passed boolean) and "skipped" (the paths of the .py files that were not run).

Notes and security

- The runner executes code on the local machine; evaluators should not run
  untrusted code. Use CI isolation or sandboxing as appropriate.
- The contract is intentionally small to reduce maintenance burden.
