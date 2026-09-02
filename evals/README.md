Eval files

- Place small, runnable Python scripts under evals/ with a .py extension.
- Eval scripts must use the Python standard library only and should be runnable
  with `python path/to/eval.py`.
- A script should perform its checks and exit with code 0 on success and non-zero
  on failure. It may print a short, human-readable summary to stdout and any
  diagnostics to stderr.

Shared note checks: evals/note_checks.py

- The per-note evals (evals/<topic>_eval.py) do not repeat the structure checks.
  Each one puts its own directory on sys.path and calls the shared helper:

      import os, sys
      sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
      from note_checks import check_note
      sys.exit(check_note("<topic>.md"))

- check_note(filename) reads notes/<filename>, prints the OK/FAIL lines and
  returns 0 (pass), 1 (a check failed) or 2 (the note could not be read).
- Fix or extend a check once, in note_checks.py, and every per-note eval picks
  it up. New per-note evals should import note_checks rather than copy it.
- Run on its own (python evals/note_checks.py, and so also by the runner) the
  module self-tests its helpers against two in-memory sample notes and exits 0.

Runner: evals/run_all.py

- Purpose: discover and execute eval scripts under evals/ and report per-file
  pass/fail status based on exit codes.
- Usage: python evals/run_all.py [--json-output FILE]
- The runner executes each eval as a separate process (same Python interpreter),
  captures stdout/stderr and returns exit code 0 if all evals passed, else 1.
- The --json-output FILE option writes an aggregated JSON summary containing
  results for each file (path, returncode, stdout, stderr, passed boolean).

Notes and security

- The runner executes code on the local machine; evaluators should not run
  untrusted code. Use CI isolation or sandboxing as appropriate.
- The contract is intentionally small to reduce maintenance burden.
