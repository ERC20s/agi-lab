"""Repository meta-eval: ensure eval scripts import only stdlib or local modules.

Usage: python3 evals/stdlib_imports_eval.py

This meta-eval scans every *_eval.py in evals/ for Import and ImportFrom
nodes anywhere in the module (not just at the top-level). It permits:
- builtin modules (sys.builtin_module_names),
- modules whose resolved origin lies under the Python stdlib directory
  (sysconfig.get_paths()['stdlib']), and
- local repository modules (when the resolved path is inside the repo root).

Relative imports (ImportFrom with a non-zero level) are ignored so package
local imports inside the repository do not produce failures.

Ambiguous or unresolved imports are WARNed and do not cause the check to
fail. A FAIL is printed only when the import resolves to a location that is
clearly outside the stdlib directory and outside the repository root.

Returns exit code 0 when no FAILs, 1 when any FAILs were emitted, 2 on major
layout errors or a failed self-check.
"""

import ast
import importlib.util
import os
import sys
import sysconfig
from pathlib import Path

# This eval checks the repository as a whole, not one note: it is exempt from
# the notes/<topic>.md pairing rule and says so here, where
# evals/note-coverage_eval.py reads it (declares_meta_eval).
META_EVAL = True

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVALS_DIR = ROOT / "evals"
EVAL_SUFFIX = "_eval.py"


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# (label, source, expected mapping or "error")
SELF_CHECK_CASES = (
    ("top-level import", "import os\n", {"os": 1}),
    ("import inside __main__", 'if __name__ == "__main__":\n    import sys\n    sys.exit(main())\n', {"sys": 2}),
    ("import inside function", "def f():\n    import requests\n    return 0\n", {"requests": 2}),
    ("import inside try/except", "try:\n    import numpy\nexcept ImportError:\n    numpy = None\n", {"numpy": 2}),
    ("import inside class body", "class C:\n    import math\n", {"math": 2}),
    ("from os import path", "from os import path\n", {"os": 1}),
    ("relative import ignored", "from . import localmod\n", {}),
    ("duplicate imports deduped", "import os\nif True:\n    import os\n", {"os": 1}),
    ("file that will not parse", "def (:\n", "error"),
)


def self_check():
    failures = []
    for label, source, expected in SELF_CHECK_CASES:
        try:
            got = top_level_imports(source)
        except SyntaxError:
            got = "error"
        except Exception as exc:
            failures.append("%s: top_level_imports raised %r" % (label, exc))
            continue
        # got is a dict name->lineno or "error"
        if got == "error":
            if expected != "error":
                failures.append("%s: expected %r, got error" % (label, expected))
            continue
        if expected == "error":
            failures.append("%s: expected error, got %r" % (label, got))
            continue
        # compare names and line numbers: expected may be subset of got but we
        # expect exact match here
        if set(got.keys()) != set(expected.keys()):
            failures.append("%s: expected names %r, got %r" % (label, sorted(expected.keys()), sorted(got.keys())))
            continue
        for name, lineno in expected.items():
            if got.get(name) != lineno:
                failures.append("%s: expected %s line %r, got %r" % (label, name, lineno, got.get(name)))
    return failures


def top_level_imports(text):
    """Return dict of import name -> first line number for Import and ImportFrom

    This walks the whole AST (ast.walk) so nested imports are seen. For Import
    nodes the top-level module name (split at dot) is used. For ImportFrom with
    a non-zero level the import is skipped (relative import); otherwise the
    module's top-level name is used.
    """
    tree = ast.parse(text)
    names = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]
                if not name:
                    continue
                lineno = getattr(node, "lineno", None)
                if name not in names or (lineno is not None and lineno < names[name]):
                    names[name] = lineno
        elif isinstance(node, ast.ImportFrom):
            if getattr(node, "level", 0) > 0:
                # relative import; allow local packages
                continue
            module = node.module
            if not module:
                continue
            name = module.split(".")[0]
            if not name:
                continue
            lineno = getattr(node, "lineno", None)
            if name not in names or (lineno is not None and lineno < names[name]):
                names[name] = lineno
    return names


def is_path_in(path, parent):
    try:
        return Path(path).resolve().is_relative_to(Path(parent).resolve())
    except AttributeError:
        # Python <3.9 fallback
        p = Path(path).resolve()
        parentp = Path(parent).resolve()
        try:
            p.relative_to(parentp)
            return True
        except Exception:
            return False


def classify_import(name, stdlib_dir):
    """Return (status, message, resolved_path_or_None).

    status is one of: "OK" (stdlib or builtin or local), "FAIL" (third-party
    resolvable outside repo and stdlib), "WARN" (could not be resolved or
    ambiguous but not clearly failing).
    """
    # Builtins
    if name in sys.builtin_module_names:
        return "OK", "builtin", None

    try:
        spec = importlib.util.find_spec(name)
    except Exception:
        # Some import machinery can raise; treat as WARN
        return "WARN", "could not run find_spec()", None

    if spec is None:
        return "WARN", "module not found (find_spec returned None)", None

    origin = getattr(spec, "origin", None)
    search_locations = getattr(spec, "submodule_search_locations", None)

    # Builtin / frozen modules
    if origin in ("built-in", "frozen") or origin is None and not search_locations:
        # origin is None with no search locations is ambiguous; warn
        if origin in ("built-in", "frozen"):
            return "OK", origin, None
        return "WARN", "spec has no origin and no search locations", None

    # If the module is a namespace package, check search locations
    if search_locations:
        for loc in list(search_locations):
            if isinstance(loc, str) and is_path_in(loc, ROOT):
                return "OK", f"local namespace package -> {loc}", loc
            if isinstance(loc, str) and stdlib_dir and is_path_in(loc, stdlib_dir):
                return "OK", f"stdlib namespace package -> {loc}", loc
        # Not evidently in stdlib or repo
        return "FAIL", f"namespace package locations not under stdlib or repo: {list(search_locations)}", list(search_locations)

    # Otherwise origin is a file path
    if isinstance(origin, str):
        origin_path = Path(origin).resolve()
        if stdlib_dir and is_path_in(origin_path, stdlib_dir):
            return "OK", f"stdlib -> {origin}", str(origin_path)
        if is_path_in(origin_path, ROOT):
            return "OK", f"local -> {origin}", str(origin_path)
        return "FAIL", f"third-party -> {origin}", str(origin_path)

    # Fallback
    return "WARN", f"unhandled spec: origin={origin}, search_locations={search_locations}", None


def main():
    # run the self-check first, same convention as the other evals
    check_failures = self_check()
    if check_failures:
        print("ERROR: self-check failed - not judging evals with a broken importer detector", file=sys.stderr)
        for failure in check_failures:
            print("  - %s" % failure, file=sys.stderr)
        return 2
    print("self-check: %d import case(s) OK" % (len(SELF_CHECK_CASES)))

    if not EVALS_DIR.is_dir():
        print("ERROR: expected directory evals/ at the repository root", file=sys.stderr)
        return 2

    stdlib_dir = None
    try:
        stdlib_dir = sysconfig.get_paths().get("stdlib")
    except Exception:
        stdlib_dir = None

    failures = 0

    for fn in sorted(os.listdir(EVALS_DIR)):
        if not fn.endswith(EVAL_SUFFIX):
            continue
        path = EVALS_DIR / fn
        try:
            text = read_text(path)
        except OSError as exc:
            print(f"FAIL: {fn} - could not read {path}: {exc}")
            failures += 1
            continue

        try:
            imports = top_level_imports(text)
        except SyntaxError as exc:
            print(f"FAIL: {fn} - could not parse ({exc})")
            failures += 1
            continue

        if not imports:
            print(f"OK: {fn} - no imports")
            continue

        file_failed = False
        for name in sorted(imports.keys()):
            lineno = imports.get(name)
            status, msg, resolved = classify_import(name, stdlib_dir)
            if status == "OK":
                print(f"OK: {fn} - import {name} (line {lineno}): {msg}")
            elif status == "WARN":
                print(f"WARN: {fn} - import {name} (line {lineno}): {msg}")
            elif status == "FAIL":
                print(f"FAIL: {fn} - import {name} (line {lineno}): {msg}")
                file_failed = True

        if file_failed:
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
