# Reproducibility practices for small stdlib-only evals

Summary: This note lists concise, practical practices for writing small Python eval scripts that are easy to run, deterministic where possible, and safe to execute locally. It targets the repo's eval contract (python3, stdlib-only, safe main() harness) and complements CONTRIBUTING.md with concrete examples and checks.

Motivation & Background:

- Small, dependency-free evals are valuable because they are easy to inspect and run, but they are also easy to make brittle (non-deterministic, slow, or unsafe). Reviewers and users waste time debugging seed/state issues, flaky I/O ordering, or long-running network calls.
- This short guide helps authors make evals that behave well in local runs and CI: deterministic by default, limited in runtime and resource expectations, and clear about success/failure conditions.

Sources:
1. https://docs.python.org/3/library/random.html
2. https://docs.python.org/3/library/subprocess.html
3. https://docs.python.org/3/library/signal.html

Reading list:
- Python stdlib docs above are primary references. See the repo's evals/README.md and evals/run_all.py for runner expectations and how the test harness executes evals.

Practical suggestions (short checklist):
- Deterministic seeds: set random.seed(0) and, if using numpy in other repos, call numpy.random.seed(0). For pure stdlib, also set PYTHONHASHSEED=0 in run instructions to stabilize dict/set ordering across runs.
- Deterministic I/O: avoid relying on filesystem iteration order. Sort lists of filenames and use stable formats (JSON lines or newline-separated records) for textual outputs.
- Time and resource limits: keep evals quick (< a few seconds). Use subprocess.run(..., timeout=SECONDS) or signal.alarm for simple timeouts. Avoid long sleeps and network calls; if needed, fail fast on missing network.
- Safe main harness: follow CONTRIBUTING.md example—wrap work in main(), print concise human-readable results, and exit with non-zero on failure.
- Assertion style: prefer programmatic numeric checks (e.g., abs(a-b) < tol) and explicit sys.exit codes over fragile string matching. Print diagnostic details to stderr.
- Security note: evals/run_all.py executes code on the local machine. Do not run untrusted evals without sandboxing; keep the contract small to reduce attack surface.

Eval:
- See evals/reproducibility-practices_eval.py

If this passes, a contributor will open a PR adding notes/reproducibility-practices.md and the group will review it against CONTRIBUTING.md's checklist.