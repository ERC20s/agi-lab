"""Verify every *_eval.py follows CONTRIBUTING.md's eval script rules.

Checks performed (repository-wide, standard library only):
- Every evals/<topic>_eval.py has a module-level docstring (ast.get_docstring).
- The file defines a top-level def main(...).
- The file's if __name__ == "__main__" block calls sys.exit(main()) (or calls
  sys.exit(...) with main() as an argument).

Returns 0 when all eval scripts pass these textual/AST checks, 1 when any file
fails, 2 if the evals/ directory cannot be read.
"""

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVALS_DIR = os.path.join(ROOT, "evals")
EVAL_SUFFIX = "_eval.py"


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def check_file(path):
    """Return (ok:bool, problems:[str]) for the given eval file path."""
    problems = []
    try:
        text = read_text(path)
    except OSError as exc:
        problems.append(f"could not read file: {exc}")
        return False, problems

    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        problems.append(f"syntax error when parsing: {exc}")
        return False, problems

    # Module docstring
    doc = ast.get_docstring(tree)
    if not doc or not doc.strip():
        problems.append("missing module-level docstring")

    # main() function
    has_main = any(isinstance(n, ast.FunctionDef) and n.name == "main" for n in tree.body)
    if not has_main:
        problems.append("no top-level def main(...) found")

    # if __name__ == '__main__' ... sys.exit(main()) check
    has_good_harness = False
    for node in tree.body:
        if isinstance(node, ast.If):
            # Look for a test that is __name__ == "__main__"
            test = node.test
            is_name_main = False
            # Various AST shapes for compare: (__name__ == "__main__")
            if isinstance(test, ast.Compare):
                left = test.left
                comparators = test.comparators
                if (
                    isinstance(left, ast.Name)
                    and left.id == "__name__"
                    and len(comparators) == 1
                    and isinstance(comparators[0], (ast.Str, ast.Constant))
                    and getattr(comparators[0], "s", getattr(comparators[0], "value", None)) == "__main__"
                ):
                    is_name_main = True
            if not is_name_main:
                continue

            # Search inside the body for sys.exit(...) with main() as an argument
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call):
                    func = inner.func
                    # sys.exit(...)
                    if (
                        isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Name)
                        and func.value.id == "sys"
                        and func.attr == "exit"
                    ):
                        # Check args: any arg that calls main()
                        for arg in inner.args:
                            if isinstance(arg, ast.Call):
                                f = arg.func
                                if isinstance(f, ast.Name) and f.id == "main":
                                    has_good_harness = True
                                    break
                        if has_good_harness:
                            break
                if has_good_harness:
                    break
        if has_good_harness:
            break

    if not has_good_harness:
        problems.append("no if __name__ == '__main__' block that calls sys.exit(main())")

    return (not problems), problems


def main():
    if not os.path.isdir(EVALS_DIR):
        print("ERROR: expected directory evals/ at the repository root", file=sys.stderr)
        return 2

    files = []
    for fn in sorted(os.listdir(EVALS_DIR)):
        if not fn.endswith(EVAL_SUFFIX):
            continue
        files.append(fn)

    if not files:
        print(f"No eval files (*{EVAL_SUFFIX}) found under evals/")
        return 2

    failed = {}
    for fn in files:
        path = os.path.join(EVALS_DIR, fn)
        ok, problems = check_file(path)
        if ok:
            print(f"OK: {fn}")
        else:
            print(f"FAIL: {fn}")
            for p in problems:
                print(f"  - {p}")
            failed[fn] = problems

    print("")
    print("scanned: %d, failed: %d" % (len(files), len(failed)))

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
