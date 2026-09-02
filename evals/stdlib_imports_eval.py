"""Check that every per-note eval uses only Python's standard library.

Usage: python3 evals/stdlib_imports_eval.py

Checks performed (repository-wide, standard library only):
- For every file matching *_eval.py under evals/ (except meta-evals), parse the
  top-level Import and ImportFrom nodes and gather the leading module names.
- For each leading module name, locate it with importlib.util.find_spec without
  importing it, and verify it is a built-in or is located under the
  standard-library directory reported by sysconfig.get_paths()['stdlib'].
- Relative imports (level > 0 or missing module in an ImportFrom) are treated
  as non-stdlib and will fail.

Returns 0 on success, 1 on an imports failure, 2 if the layout cannot be read.
"""

import ast
import importlib.util
import importlib.machinery
import os
import sys
import sysconfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVALS_DIR = os.path.join(ROOT, "evals")
EVAL_SUFFIX = "_eval.py"

# Meta-evals: these validate the repository as a whole and are not per-note.
# Keep this list in sync with evals/note-coverage_eval.py's META_EVALS.
META_EVALS = {"note-coverage_eval.py", "note-format_eval.py", "eval-conformance_eval.py", "stdlib_imports_eval.py"}


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def top_level_imports(text):
    """Return a sorted set of leading module names imported at the top level.
    Only nodes that are direct children of the module (tree.body) are considered.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None, ["syntax error when parsing file"]

    mods = set()
    problems = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]
                mods.add(name)
        elif isinstance(node, ast.ImportFrom):
            # Relative import: level > 0 or missing module -> treat as non-stdlib
            if getattr(node, "level", 0) and node.level > 0:
                problems.append("relative import (level %d)" % node.level)
                continue
            if node.module is None:
                problems.append("relative import (module is None)")
                continue
            name = node.module.split(".")[0]
            mods.add(name)
    return sorted(mods), problems


def is_stdlib_module(name, stdlib_dir):
    """Return (ok:bool, reason:str or None)."""
    spec = importlib.util.find_spec(name)
    if spec is None:
        return False, "module not found"

    # Built-in modules often have origin 'built-in' or None and a builtin loader.
    origin = getattr(spec, "origin", None)
    loader = getattr(spec, "loader", None)

    if origin == "built-in":
        return True, None
    if origin is None and isinstance(loader, importlib.machinery.BuiltinImporter.__class__):
        return True, None

    # Namespace packages may have submodule_search_locations
    locations = getattr(spec, "submodule_search_locations", None)
    if locations:
        for loc in locations:
            try:
                r = os.path.realpath(loc)
            except Exception:
                r = loc
            if not r.startswith(stdlib_dir):
                return False, f"located outside stdlib: {loc}"
        return True, None

    # Otherwise, origin should be a file path; check it is under the stdlib dir.
    try:
        real = os.path.realpath(origin) if origin else origin
    except Exception:
        real = origin
    if not real:
        # Conservatively fail when we cannot resolve an origin
        return False, f"cannot resolve origin: {origin}"

    if "site-packages" in real or "dist-packages" in real:
        return False, f"located in third-party packages: {real}"

    if real.startswith(stdlib_dir):
        return True, None

    return False, f"located outside stdlib: {real}"


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

    stdlib_dir = sysconfig.get_paths().get("stdlib") or ""
    stdlib_dir = os.path.realpath(stdlib_dir)

    failed = {}

    for fn in files:
        if fn in META_EVALS:
            print(f"OK: {fn} - meta-eval, skipped")
            continue
        path = os.path.join(EVALS_DIR, fn)
        try:
            text = read_text(path)
        except OSError as exc:
            print(f"FAIL: {fn} - could not read file: {exc}")
            failed[fn] = [f"could not read file: {exc}"]
            continue

        mods, parse_problems = top_level_imports(text)
        if mods is None:
            print(f"FAIL: {fn}")
            for p in parse_problems:
                print(f"  - {p}")
            failed[fn] = parse_problems
            continue

        problems = []
        if parse_problems:
            problems.extend(parse_problems)

        for m in mods:
            ok, reason = is_stdlib_module(m, stdlib_dir)
            if not ok:
                problems.append(f"{m}: {reason}")

        if not problems:
            print(f"OK: {fn}")
        else:
            print(f"FAIL: {fn}")
            for p in problems:
                print(f"  - {p}")
            failed[fn] = problems

    print("")
    print("scanned: %d, failed: %d" % (len([f for f in files if f not in META_EVALS]), len(failed)))

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
