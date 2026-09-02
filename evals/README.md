Eval files

- Place small, runnable Python scripts under evals/ named evals/<topic>_eval.py
  (the filename rule in CONTRIBUTING.md). Only files ending in _eval.py are run.
- Eval scripts must use the Python standard library only and should be runnable
  with `python path/to/eval.py`.
- A script should perform its checks and exit with code 0 on success and non-zero
  on failure. It may print a short, human-readable summary to stdout and any
  diagnostics to stderr.

Repository-wide evals: evals/note-coverage_eval.py and evals/note-format_eval.py

- Most evals here validate one hard-coded note. note-coverage_eval.py validates
  the set: it walks notes/*.md and evals/*_eval.py, derives the topic from each
  filename and fails when a note has no evals/<topic>_eval.py, when an eval has
  no notes/<topic>.md, or when an evals/... path named in a note's Eval section
  does not exist. It prints one OK/FAIL line per topic, so a failure names the
  file to fix.
- The new note-format_eval.py is a meta-eval that checks each note's internal
  structure against CONTRIBUTING.md: it verifies an H1 title, a non-empty
  Summary, a Motivation & Background section, a Sources section that contains
  at least one http(s):// URL inside the Sources section only, and that the
  note's Eval section names the matching evals/<topic>_eval.py. It prints one
  OK/FAIL line per note and exits non-zero when any note fails.
- Both meta-evals follow the same contract as every other eval (stdlib only,
  module docstring, main() harness, exit 0 on success) and are discovered by
  run_all.py like any other *_eval.py. When adding a new meta-eval, add its
  filename to the META_EVALS set in evals/note-coverage_eval.py so it is exempt
  from the note-pairing rule.

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
