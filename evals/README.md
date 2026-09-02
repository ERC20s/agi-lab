Eval files

- Place small, runnable Python scripts under evals/ with a .py extension.
- Eval scripts must use the Python standard library only and should be runnable
  with `python path/to/eval.py`.
- A script should perform its checks and exit with code 0 on success and non-zero
  on failure. It may print a short, human-readable summary to stdout and any
  diagnostics to stderr.
- Evals never read stdin. The runner starts every script with stdin closed
  (subprocess.DEVNULL), so a call to input() fails immediately instead of
  waiting forever. An eval that needs input should read a file under the
  repository instead.
- An eval should finish well inside the runner's per-eval time limit (60 seconds
  by default). Keep them small and offline.

Runner: evals/run_all.py

- Purpose: discover and execute eval scripts under evals/ and report per-file
  pass/fail status based on exit codes.
- Usage: python evals/run_all.py [--timeout SECONDS] [--json-output FILE]
- The runner executes each eval as a separate process (same Python interpreter),
  with stdin closed, captures stdout/stderr and reports each file as PASS, FAIL
  or TIMEOUT. It ends with a summary line: "N passed, M failed, K timed out".
- --timeout SECONDS sets the wall-clock limit for each eval. The default is 60
  seconds; --timeout 0 disables the limit. An eval that runs past the limit is
  killed and reported as TIMEOUT (not passed), keeping whatever output it had
  produced, with a stderr line naming the limit.
- The --json-output FILE option writes an aggregated JSON summary containing
  results for each file (path, returncode, stdout, stderr, passed boolean and
  timed_out boolean). returncode is null for an eval that timed out or that the
  runner could not start.
- Exit codes: 0 when every eval passed; 1 when any eval failed or timed out;
  2 when every eval passed but the --json-output summary could not be written
  (a lost report is never reported as a clean run).

Notes and security

- The runner executes code on the local machine; evaluators should not run
  untrusted code. Use CI isolation or sandboxing as appropriate.
- The contract is intentionally small to reduce maintenance burden.
