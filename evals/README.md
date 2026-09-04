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
- Both Eval styles are checked. note-coverage_eval.py's EVAL_HEADER_RE now
  matches the label and its colon only (`^Eval\b[ \t]*:?[ \t]*`, the same shape
  note-format_eval.py uses), so an inline "Eval: See evals/foo_eval.py" line
  keeps its reference in the section body instead of being read as an empty
  section whose paths were never checked. Before any note is judged the script
  runs self_check() over SELF_CHECK_CASES — an inline Eval line, a block Eval
  header with the reference below, a header at the end of the file, an inline
  header followed by a later section, and a missing header — and exits 2 with
  the expected and actual body on stderr rather than passing notes with a broken
  extractor. Known limitation: SECTION_END_RE still ends a section only at a
  label alone on its line, so an inline header directly after Eval leaves the
  body over-long; that over-includes rather than under-checks.
- note-format_eval.py is a meta-eval that checks each note's top-level
  sections and that the Eval: section points at an existing eval script. It
  reuses the same section-boundary and eval-path heuristics as
  note-coverage_eval.py to reduce false positives. When a note lacks an explicit
  "Sources:" section but contains a URL elsewhere the meta-eval emits a
  non-failing warning suggesting the URL be moved into Sources; when a
  Sources: section is present it must include at least one http(s) URL.
- Section bodies are read in both of the styles CONTRIBUTING.md's template
  allows. The header regexes (SUMMARY_HEADER_RE, MOTIVATION_HEADER_RE,
  SOURCES_HEADER_RE, EVAL_HEADER_RE) match the label and its colon only, never
  the rest of the line, so extract_section returns the remainder of the header
  line plus everything up to the next section header. The inline form
  ("Summary: two sentences ...") that every note in notes/ uses therefore passes,
  where before the body was cut at the end of the header line and the note was
  failed with "empty Summary section". A section whose inline remainder and body
  are both blank is still reported as empty, so a genuinely missing Summary
  still fails.
- Before any note is judged, note-format_eval.py runs self_check() over
  SELF_CHECK_CASES: fixture strings covering an inline header, a header with the
  body below it, a header at the end of the file, an inline header with more
  lines under it, a missing header, and the inline forms of Sources, Motivation
  & Background and Eval. A wrong extraction prints the expected and actual body
  to stderr and exits 2 (the same code used for layout errors) instead of
  blaming the notes.
- runner_eval.py is the self-test for the runner. It loads evals/run_all.py by
  path (importlib.util.spec_from_file_location, so no new import name) and
  checks its behaviour against throwaway fixtures in a temporary directory:
  discover_eval_files runs only *_eval.py and skips other .py files while
  ignoring __init__.py and __pycache__/; run_file reports a non-zero exit as a
  failure with a numeric duration_seconds; a sleeping script under a 0.5s
  timeout comes back timed_out with "exceeded the" in stderr; a script calling
  input() fails instead of hanging; write_json produces parsable JSON whose
  summary carries all_passed, total, passed, failed, timed_out, timeout_seconds,
  total_duration_seconds, runner_version and timestamp and returns True;
  write_json creates a missing parent directory, returns False instead of
  raising when the output path is impossible (its parent is a regular file), and
  leaves an existing valid last_run.json byte-for-byte intact with no temporary
  file behind when a write fails; and positive_timeout
  rejects "0", "-1" and "abc". It prints one OK/FAIL line per check. Because it
  names run_all.py's functions directly, a future rename in the runner has to be
  made here too.
- These files follow the usual eval contract (stdlib only, module docstring,
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
- Timing: every eval is timed with time.perf_counter() around its subprocess.
  The report line now reads `[PASS] topic_eval.py (exit=0, 0.042s)` and ends
  with a `N eval(s) in X.XXXs total` line.
- JSON output (--json-output, run: writes evals/last_run.json): each entry of
  "results" carries duration_seconds (float, wall-clock seconds including
  interpreter start-up, rounded to milliseconds) and "summary" carries
  total_duration_seconds alongside all_passed, total, passed, failed,
  timed_out, timeout_seconds, runner_version and timestamp. That schema change
  is why runner_version is "0.2"; a consumer pinned to "0.1" should be updated.
- A failed --json-output write now fails the run. write_json returns True or
  False (the reason goes to stderr, never an exception), and when a summary was
  asked for and not written the runner exits non-zero even though every eval
  passed — a run whose summary nobody can read must not report green. The write
  is atomic: the payload is serialised in memory, written to a temporary file in
  the target's own directory and os.replace()d over it, and a missing parent
  directory named on --json-output is created first. So evals/last_run.json is
  either the previous run or this one, never a truncated file. The JSON schema
  does not change, so runner_version stays "0.2". The trade-off: a caller that
  passes --json-output but does not care about the file now sees exit 1 when the
  path is unwritable.

Notes and security

- The runner executes code on the local machine; evaluators should not run
  untrusted code. Use CI isolation or sandboxing as appropriate.
- The contract is intentionally small to reduce maintenance burden.
