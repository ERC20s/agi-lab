Eval files

- Place small, runnable Python scripts under evals/ named evals/<topic>_eval.py
  (the filename rule in CONTRIBUTING.md). Only files ending in _eval.py are run.
- Eval scripts must use the Python standard library only and should be runnable
  with `python path/to/eval.py`.
- A script should perform its checks and exit with code 0 on success and non-zero
  on failure. It may print a short, human-readable summary to stdout and any
  diagnostics to stderr.

Repository-wide evals

- note-coverage_eval.py validates the set: it walks notes/*.md and evals/*_eval.py, derives the topic from each
  filename and fails when a note has no evals/<topic>_eval.py, when an eval has
  no notes/<topic>.md, or when an evals/... path named in a note's Eval section
  does not exist. It prints one OK/FAIL line per topic, so a failure names the
  file to fix.
- note-format_eval.py is a new meta-eval that checks each note's top-level
  sections and that the Eval: section points at an existing eval script. It
  reuses the same section-boundary and eval-path heuristics as
  note-coverage_eval.py to reduce false positives. When a note lacks an explicit
  "Sources:" section but contains a URL elsewhere the meta-eval emits a
  non-failing warning suggesting the URL be moved into Sources; when a
  Sources: section is present it must include at least one http(s) URL.
- Both files follow the usual eval contract (stdlib only, module docstring,
  main() harness, exit 0 on success) and are discovered and run by
  evals/run_all.py like any other *_eval.py. Add a new meta-eval's filename to
  the META_EVALS set in evals/note-coverage_eval.py so it is exempt from the
  per-note pairing rule.

Runner: evals/run_all.py

- Purpose: discover and execute eval scripts under evals/ and report per-file
  pass/fail status based on exit codes.
- Usage: python evals/run_all.py [--json-output FILE] [--timeout SECONDS]
- Discovery rule: only files whose name ends in _eval.py are executed. The
  runner itself, __init__.py and __pycache__ are excluded as before. Any other
  .py file under evals/ — a shared helper module, a scratch file — is skipped:
  it is never executed, never counted as a pass, and never fails the run.

Notes and security

- The runner executes code on the local machine; evaluators should not run
  untrusted code. Use CI isolation or sandboxing as appropriate.
- The contract is intentionally small to reduce maintenance burden.
