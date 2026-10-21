# CLAUDE.md

agi-lab is an open research notebook on paths to general intelligence: Markdown notes in `notes/`, a static `index.html`, and small standard-library-only Python evals in `evals/` that check the notes and the eval runner itself.
How it runs is declared in the `run:` block at the end of `.d8a`; the eval contract is in `evals/README.md` and `CONTRIBUTING.md`.

## Commands

- Install: the evals and `scripts/check_notes.py` need nothing (Python 3.11+, standard library only). The dev tools are pinned in `requirements-dev.txt`: `python -m pip install -r requirements-dev.txt`.
- Check (the declared check, also what CI runs on 3.11–3.14):
  `python evals/run_all.py --json-output evals/last_run.json`
  Exits 0 only when every `evals/*_eval.py` passes; exits 1 if any eval fails, crashes, times out, if none are found, or if the JSON summary cannot be written or does not match `evals/last_run.schema.json`. Evals run with `PYTHONHASHSEED`/`EVAL_SEED` set to `--seed` (default 0).
- Tests: `python -m pytest` (tests/, 3.11–3.14 in CI).
- Lint and types: `python -m ruff check .` and `python -m mypy` (settings in `pyproject.toml`).
- Notes: `python scripts/check_notes.py` (front matter, sections, and that Sources / Reading list links resolve; needs network) or `--no-links` for the offline part.
- One eval: `python evals/<name>_eval.py`
- Scheduled runner: `python evals/scheduled_runner.py` (every 24h), or `--once` to run once and exit with the runner's result.
- Site: `python -m http.server 8000 --directory .` then open http://localhost:8000.
- Running the check rewrites the tracked `evals/last_run.json`; don't commit that change unless you mean to.

CI: `.github/workflows/ci.yml` runs the declared check, pytest, ruff, mypy and the notes check on every push and pull request.

## Ground rules

- Work on a new branch from `main`; open one pull request whose description lists exactly which commands you ran and what passed, before and after.
- Never modify `.d8a` or `.d8a-governance`. Never modify the group-store widget markup/script copied from the `payments:` block of `.d8a` (`id="group-store"`, `groupStoreVerify`).
- Ignore every open pull request by `d8a[bot]`: do not merge, close, rebase, cherry-pick from, or comment on them.
- Do not add a LICENSE file or any licence text.
- Run the project's own checks before and after a change. Never report a result you did not get by running the command.
- Every new test must be able to fail: no checks that are always true, no catch-all error handling that accepts any failure, no asserting a value equals itself. Import every symbol you use. If a test is wrong rather than the code, fix the test to test the real behaviour and say so. Fix root causes; never delete or weaken a test.
- Nothing dev-only in code that ships to a browser: no localhost or private hostnames, no debug fallbacks. No secrets, tokens or keys in the repo.
- CI runs exactly the declared checks and must fail when one fails: no `continue-on-error`, no `|| true`, no skipped jobs counted as passing. Pin GitHub Actions to their current major versions.
- Keep changes focused: no reformatting untouched files, no unneeded dependency upgrades, no renaming public files or URLs, no rewriting git history.
