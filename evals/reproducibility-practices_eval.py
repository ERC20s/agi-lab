"""Lint evals/ scripts against notes/reproducibility-practices.md's checklist.

Usage: python3 evals/reproducibility-practices_eval.py

For every *.py file directly under evals/ (excluding this file itself and
evals/run_all.py, and skipping __pycache__ and __init__.py the same way
evals/run_all.py does), checks that the file textually appears to follow
the "Safe main harness" checklist item from
notes/reproducibility-practices.md:

- a module-level docstring is present (file starts with \"\"\" or ''' after
  optional leading whitespace/comments)
- a `def main(` function is defined
- the file ends with an `if __name__ == "__main__":` guard that calls
  `sys.exit(main())`

This is advisory, textual/regex-based linting only: it does not import or
execute the target files, so it cannot false-fail on side effects, but it
can also be fooled by unusual-but-valid styles (see the note's Risks
discussion).

Prints per-file OK/FAIL lines and exits 0 only if every discovered eval
file passes all three checks, non-zero otherwise, per evals/README.md's
exit-code contract.
"""

import os
import re
import sys

EVALS_DIR = os.path.abspath(os.path.dirname(__file__))
THIS_FILE = os.path.abspath(__file__)
RUNNER_FILE = os.path.join(EVALS_DIR, "run_all.py")

DOCSTRING_RE = re.compile(r'^\s*("""|\'\'\')')
MAIN_DEF_RE = re.compile(r'^\s*def\s+main\s*\(')
GUARD_RE = re.compile(
    r'if\s+__name__\s*==\s*["\']__main__["\']\s*:\s*\n\s*sys\.exit\(\s*main\(\s*\)\s*\)'
)


def discover_target_files(root_dir):
    files = []
    for fn in sorted(os.listdir(root_dir)):
        full = os.path.join(root_dir, fn)
        if not os.path.isfile(full):
            continue
        if not fn.endswith(".py"):
            continue
        if fn == "__init__.py":
            continue
        if os.path.abspath(full) == THIS_FILE:
            continue
        if os.path.abspath(full) == os.path.abspath(RUNNER_FILE):
            continue
        files.append(full)
    return files


def check_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except Exception as e:
        return [f"ERROR: could not read {path}: {e}"], False

    problems = []

    if not DOCSTRING_RE.match(text):
        problems.append("missing a module-level docstring at top of file")

    if not MAIN_DEF_RE.search(text):
        problems.append("missing a 'def main(' function definition")

    if not GUARD_RE.search(text):
        problems.append(
            'missing an \'if __name__ == "__main__": sys.exit(main())\' guard'
        )

    return problems, len(problems) == 0


def main():
    targets = discover_target_files(EVALS_DIR)

    if not targets:
        print("No other eval files (*.py) found under evals/ to check")
        return 0

    all_ok = True
    for path in targets:
        rel = os.path.relpath(path, start=EVALS_DIR)
        problems, ok = check_file(path)
        if ok:
            print(f"OK: {rel}")
        else:
            all_ok = False
            print(f"FAIL: {rel}")
            for p in problems:
                print(f"  - {p}", file=sys.stderr)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
